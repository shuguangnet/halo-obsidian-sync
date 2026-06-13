import { App, Notice, Plugin, PluginSettingTab, Setting, TFile, Menu, Platform, requestUrl, MetadataCache } from "obsidian";

// ==================== 插件设置 ====================

interface HaloSyncSettings {
	haloBaseUrl: string;
	haloPatToken: string;
	defaultVisible: string;
	autoPublish: boolean;
	showStatusBar: boolean;
}

const DEFAULT_SETTINGS: HaloSyncSettings = {
	haloBaseUrl: "",
	haloPatToken: "",
	defaultVisible: "PUBLIC",
	autoPublish: true,
	showStatusBar: true,
};

// ==================== Halo API 客户端 ====================

class HaloApiClient {
	baseUrl: string;
	token: string;

	constructor(baseUrl: string, token: string) {
		this.baseUrl = baseUrl.replace(/\/$/, "");
		this.token = token;
	}

	async request(method: string, path: string, body?: any, headers?: Record<string, string>): Promise<any> {
		const url = `${this.baseUrl}${path}`;
		const reqHeaders: Record<string, string> = {
			"Authorization": `Bearer ${this.token}`,
			"Accept": "application/json",
			...headers,
		};

		if (body && typeof body === "object" && !(body instanceof FormData) && !(body instanceof Uint8Array)) {
			reqHeaders["Content-Type"] = "application/json";
		}

		try {
			const resp = await requestUrl({
				url,
				method: method as any,
				headers: reqHeaders,
				body: body ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined,
			});

			if (resp.status >= 400) {
				throw new Error(`HTTP ${resp.status}: ${resp.text || ""}`);
			}
			return resp.json;
		} catch (err: any) {
			if (err.status === 401) {
				throw new Error("认证失败：请检查 Halo Personal Access Token 是否有效");
			}
			throw new Error(`Halo API 错误: ${err.message || err}`);
		}
	}

	async listPosts(page = 0, size = 20, keyword?: string): Promise<any> {
		const params = new URLSearchParams({ page: String(page), size: String(size) });
		if (keyword) params.append("keyword", keyword);
		return this.request("GET", `/apis/api.console.halo.run/v1alpha1/posts?${params.toString()}`);
	}

	async getPost(name: string): Promise<any> {
		return this.request("GET", `/apis/api.console.halo.run/v1alpha1/posts/${name}`);
	}

	async createPost(postBody: any): Promise<any> {
		return this.request("POST", "/apis/api.console.halo.run/v1alpha1/posts", postBody);
	}

	async updatePost(name: string, postBody: any): Promise<any> {
		return this.request("PUT", `/apis/api.console.halo.run/v1alpha1/posts/${name}`, postBody);
	}

	async publishPost(name: string): Promise<any> {
		return this.request("PUT", `/apis/api.console.halo.run/v1alpha1/posts/${name}/publish`);
	}

	async unpublishPost(name: string): Promise<any> {
		return this.request("PUT", `/apis/api.console.halo.run/v1alpha1/posts/${name}/unpublish`);
	}

	async uploadAttachment(fileData: ArrayBuffer, filename: string, mimeType: string): Promise<any> {
		const boundary = "----FormBoundary" + Math.random().toString(36).slice(2);
		const encoder = new TextEncoder();

		// Build multipart body
		const pre = encoder.encode(
			`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${filename}"\r\nContent-Type: ${mimeType}\r\n\r\n`
		);
		const post = encoder.encode(`\r\n--${boundary}--\r\n`);

		const body = new Uint8Array(pre.length + fileData.byteLength + post.length);
		body.set(pre, 0);
		body.set(new Uint8Array(fileData), pre.length);
		body.set(post, pre.length + fileData.byteLength);

		const url = `${this.baseUrl}/apis/api.core.halo.run/v1alpha1/attachments`;
		try {
			const resp = await requestUrl({
				url,
				method: "POST",
				headers: {
					"Authorization": `Bearer ${this.token}`,
					"Content-Type": `multipart/form-data; boundary=${boundary}`,
				},
				body: body.buffer,
			});
			if (resp.status >= 400) {
				throw new Error(`HTTP ${resp.status}: ${resp.text || ""}`);
			}
			return resp.json;
		} catch (err: any) {
			throw new Error(`附件上传失败: ${err.message || err}`);
		}
	}

	async listTags(page = 0, size = 50): Promise<any> {
		const params = new URLSearchParams({ page: String(page), size: String(size) });
		return this.request("GET", `/apis/api.console.halo.run/v1alpha1/tags?${params.toString()}`);
	}

	async listCategories(page = 0, size = 50): Promise<any> {
		const params = new URLSearchParams({ page: String(page), size: String(size) });
		return this.request("GET", `/apis/api.console.halo.run/v1alpha1/categories?${params.toString()}`);
	}
}

// ==================== 同步引擎 ====================

class SyncEngine {
	app: App;
	client: HaloApiClient;
	settings: HaloSyncSettings;

	constructor(app: App, client: HaloApiClient, settings: HaloSyncSettings) {
		this.app = app;
		this.client = client;
		this.settings = settings;
	}

	/**
	 * 解析笔记元数据
	 */
	async parseNote(file: TFile): Promise<{ meta: Record<string, any>; content: string; shouldSync: boolean }> {
		const cache = this.app.metadataCache.getFileCache(file);
		const meta = cache?.frontmatter || {};
		const content = await this.app.vault.cachedRead(file) || "";

		return {
			meta,
			content,
			shouldSync: !!meta["halo_sync"],
		};
	}

	/**
	 * 提取正文中的图片引用
	 */
	extractImages(content: string): string[] {
		const images: string[] = [];
		// Obsidian WikiLink: ![[image.png]]
		const wikiRegex = /!?\[\[([^\]|]+)(?:\|[^\]]*)?\]\]/g;
		let match;
		while ((match = wikiRegex.exec(content)) !== null) {
			images.push(match[1].trim());
		}
		// 标准 Markdown: ![alt](path)
		const mdRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
		while ((match = mdRegex.exec(content)) !== null) {
			const path = match[2].trim();
			if (!path.startsWith("http://") && !path.startsWith("https://")) {
				images.push(path);
			}
		}
		return [...new Set(images)];
	}

	/**
	 * 解析图片引用为 Vault 内绝对路径
	 */
	resolveImagePath(imageRef: string, noteDir: string): string | null {
		const vault = this.app.vault;
		const candidates = [
			`${noteDir}/${imageRef}`,
			imageRef,
			`attachments/${imageRef}`,
			`Images/${imageRef}`,
			`images/${imageRef}`,
		];
		for (const cand of candidates) {
			const file = vault.getAbstractFileByPath(cand);
			if (file && file instanceof TFile) {
				return cand;
			}
		}
		return null;
	}

	/**
	 * 处理附件上传，替换正文中的图片链接
	 */
	async processAttachments(content: string, noteDir: string): Promise<string> {
		const images = this.extractImages(content);
		let processed = content;

		for (const imgRef of images) {
			const resolvedPath = this.resolveImagePath(imgRef, noteDir);
			if (!resolvedPath) {
				console.warn(`[警告] 找不到图片: ${imgRef}`);
				continue;
			}

			const file = this.app.vault.getAbstractFileByPath(resolvedPath);
			if (!file || !(file instanceof TFile)) continue;

			try {
				const binary = await this.app.vault.readBinary(file);
				const mime = this.guessMime(file.extension);
				const att = await this.client.uploadAttachment(binary, file.name, mime);
				const permalink = att?.spec?.permalink || att?.spec?.url;
				if (permalink) {
					processed = this.replaceImageRef(processed, imgRef, permalink);
				}
			} catch (err) {
				console.warn(`[警告] 上传图片 ${imgRef} 失败:`, err);
			}
		}

		return processed;
	}

	replaceImageRef(content: string, oldRef: string, newUrl: string): string {
		// 替换 WikiLink
		content = content.replace(
			new RegExp(`!?\\[\\[${this.escapeRegExp(oldRef)}(\\|[^\\]]*)?\\]\\]`, "g"),
			`![${oldRef.split("/").pop() || oldRef}](${newUrl})`
		);
		// 替换标准 Markdown
		content = content.replace(
			new RegExp(`!\\[([^\\]]*)\\]\\(${this.escapeRegExp(oldRef)}\\)`, "g"),
			`![\$1](${newUrl})`
		);
		return content;
	}

	escapeRegExp(s: string): string {
		return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	}

	guessMime(ext: string): string {
		const map: Record<string, string> = {
			png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
			gif: "image/gif", svg: "image/svg+xml", webp: "image/webp",
			mp4: "video/mp4", pdf: "application/pdf", zip: "application/zip",
		};
		return map[ext.toLowerCase()] || "application/octet-stream";
	}

	/**
	 * 构建 Halo Post 对象
	 */
	buildPostBody(meta: Record<string, any>, content: string, visible: string): any {
		const title = meta["title"] || "";
		const slug = meta["slug"] || this.toSlug(title);
		const tags = this.normalizeList(meta["tags"]);
		const categories = this.normalizeList(meta["categories"]);
		const excerpt = meta["excerpt"] || meta["description"] || "";

		const body: any = {
			spec: {
				title,
				slug,
				content,
				visible,
			},
			metadata: {},
		};

		if (tags.length > 0) body.spec.tags = tags;
		if (categories.length > 0) body.spec.categories = categories;
		if (excerpt) {
			body.spec.excerpt = {
				autoGenerate: false,
				raw: excerpt,
			};
		}

		return body;
	}

	normalizeList(val: any): string[] {
		if (!val) return [];
		if (Array.isArray(val)) return val.map(String);
		if (typeof val === "string") return val.split(",").map((s) => s.trim()).filter(Boolean);
		return [];
	}

	toSlug(text: string): string {
		return text
			.replace(/[^\u4e00-\u9fa5a-zA-Z0-9_-]/g, "-")
			.replace(/-+/g, "-")
			.replace(/^-|-$/g, "")
			.toLowerCase()
			.slice(0, 100);
	}

	/**
	 * 主同步函数
	 */
	async syncNote(file: TFile, force = false): Promise<{ status: string; postName?: string; message: string }> {
		const { meta, content, shouldSync } = await this.parseNote(file);

		if (!shouldSync) {
			return { status: "skipped", message: "halo_sync 未设置为 true，跳过" };
		}

		const postName = meta["halo_post_name"];
		const lastSync = meta["halo_last_sync"];

		// 检查是否需要更新
		if (!force && postName && lastSync) {
			const mtime = file.stat.mtime;
			const syncTime = new Date(lastSync).getTime();
			if (!isNaN(syncTime) && mtime <= syncTime) {
				return { status: "skipped", postName, message: "文件未变更，跳过" };
			}
		}

		// 处理附件
		const noteDir = file.parent?.path || "";
		let processedContent: string;
		try {
			processedContent = await this.processAttachments(content, noteDir);
		} catch (err) {
			return { status: "error", postName, message: `附件处理失败: ${err}` };
		}

		// 构建请求体
		const postBody = this.buildPostBody(meta, processedContent, this.settings.defaultVisible);
		let status: string;
		let resultPostName: string | undefined;

		try {
			if (postName) {
				// 更新
				try {
					const existing = await this.client.getPost(postName);
					if (existing) {
						postBody.metadata = existing.metadata || {};
						await this.client.updatePost(postName, postBody);
						if (meta["halo_status"] === "published") {
							await this.client.publishPost(postName);
						}
						status = "updated";
						resultPostName = postName;
					} else {
						// 服务端不存在，重新创建
						postBody.metadata = {};
						const created = await this.client.createPost(postBody);
						resultPostName = created.metadata?.name;
						if (meta["halo_status"] === "published") {
							await this.client.publishPost(resultPostName!);
						}
						status = "created";
					}
				} catch (err) {
					// 获取失败，重新创建
					postBody.metadata = {};
					const created = await this.client.createPost(postBody);
					resultPostName = created.metadata?.name;
					if (meta["halo_status"] === "published") {
						await this.client.publishPost(resultPostName!);
					}
					status = "created";
				}
			} else {
				// 新建
				postBody.metadata = {};
				const created = await this.client.createPost(postBody);
				resultPostName = created.metadata?.name;
				if (meta["halo_status"] === "published" || this.settings.autoPublish) {
					await this.client.publishPost(resultPostName!);
				}
				status = "created";
			}
		} catch (err: any) {
			return { status: "error", postName: resultPostName, message: `Halo API 错误: ${err.message || err}` };
		}

		// 回写本地 frontmatter
		const now = new Date().toISOString();
		await this.updateFrontmatter(file, {
			"halo_post_name": resultPostName,
			"halo_status": meta["halo_status"] || (this.settings.autoPublish ? "published" : "draft"),
			"halo_last_sync": now,
		});

		return { status, postName: resultPostName, message: `${status}: ${meta["title"] || file.name}` };
	}

	async updateFrontmatter(file: TFile, updates: Record<string, any>): Promise<void> {
		// 使用 app.fileManager.processFrontMatter 更新笔记元数据
		await this.app.fileManager.processFrontMatter(file, (frontmatter) => {
			for (const [key, value] of Object.entries(updates)) {
				frontmatter[key] = value;
			}
		});
	}
}

// ==================== 插件主体 ====================

export default class HaloObsidianSyncPlugin extends Plugin {
	settings: HaloSyncSettings;
	statusBarItemEl: HTMLElement | null = null;
	client: HaloApiClient | null = null;
	engine: SyncEngine | null = null;

	async onload() {
		await this.loadSettings();

		// 初始化 API 客户端
		this.initClient();

		// 注册设置面板
		this.addSettingTab(new HaloSyncSettingTab(this.app, this));

		// 注册命令
		this.addCommand({
			id: "halo-sync-current-note",
			name: "同步当前笔记到 Halo",
			editorCallback: (editor, ctx) => {
				const file = ctx.file;
				if (file) {
					this.syncCurrentNote(file);
				}
			},
		});

		this.addCommand({
			id: "halo-sync-force-current-note",
			name: "强制重新同步当前笔记到 Halo",
			editorCallback: (editor, ctx) => {
				const file = ctx.file;
				if (file) {
					this.syncCurrentNote(file, true);
				}
			},
		});

		this.addCommand({
			id: "halo-sync-all-notes",
			name: "批量同步所有标记的笔记到 Halo",
			callback: () => {
				this.syncAllNotes();
			},
		});

		// 注册右键菜单
		this.registerEvent(
			this.app.workspace.on("file-menu", (menu, file) => {
				if (file instanceof TFile && file.extension === "md") {
					menu.addItem((item) => {
						item
							.setTitle("同步到 Halo")
							.setIcon("upload")
							.onClick(() => {
								this.syncCurrentNote(file);
							});
					});
				}
			})
		);

		// 状态栏
		if (this.settings.showStatusBar) {
			this.statusBarItemEl = this.addStatusBarItem();
			this.statusBarItemEl.setText("📰 Halo");
			this.statusBarItemEl.addClass("halo-sync-status-bar");
			this.statusBarItemEl.onClickEvent(() => {
				const activeFile = this.app.workspace.getActiveFile();
				if (activeFile) {
					this.syncCurrentNote(activeFile);
				}
			});
		}

		console.log("[Halo Obsidian Sync] 插件已加载");
	}

	onunload() {
		console.log("[Halo Obsidian Sync] 插件已卸载");
	}

	initClient() {
		if (this.settings.haloBaseUrl && this.settings.haloPatToken) {
			this.client = new HaloApiClient(this.settings.haloBaseUrl, this.settings.haloPatToken);
			this.engine = new SyncEngine(this.app, this.client, this.settings);
		} else {
			this.client = null;
			this.engine = null;
		}
	}

	async syncCurrentNote(file: TFile, force = false) {
		if (!this.engine) {
			new Notice("[错误] Halo 配置未完成，请先在设置中填写地址和 Token", 5000);
			return;
		}

		new Notice(`🔄 正在同步: ${file.name}...`);
		try {
			const result = await this.engine.syncNote(file, force);
			if (result.status === "created" || result.status === "updated") {
				new Notice(`✅ 同步成功: ${result.message}`, 4000);
				this.updateStatusBar(file, result.status);
			} else if (result.status === "skipped") {
				new Notice(`⏭️ 已跳过: ${result.message}`, 3000);
			} else {
				new Notice(`❌ 同步失败: ${result.message}`, 5000);
			}
		} catch (err: any) {
			new Notice(`❌ 同步异常: ${err.message || err}`, 5000);
			console.error("[Halo Sync] 同步异常:", err);
		}
	}

	async syncAllNotes() {
		if (!this.engine) {
			new Notice("[错误] Halo 配置未完成", 5000);
			return;
		}

		const files = this.app.vault.getMarkdownFiles();
		const syncFiles: TFile[] = [];

		for (const file of files) {
			const cache = this.app.metadataCache.getFileCache(file);
			if (cache?.frontmatter?.["halo_sync"] === true) {
				syncFiles.push(file);
			}
		}

		if (syncFiles.length === 0) {
			new Notice("没有找到标记了 halo_sync: true 的笔记", 3000);
			return;
		}

		new Notice(`🔄 开始批量同步 ${syncFiles.length} 篇笔记...`);
		let created = 0, updated = 0, skipped = 0, errors = 0;

		for (const file of syncFiles) {
			try {
				const result = await this.engine!.syncNote(file);
				if (result.status === "created") created++;
				else if (result.status === "updated") updated++;
				else if (result.status === "skipped") skipped++;
				else errors++;
			} catch (err) {
				errors++;
				console.error(`[Halo Sync] 同步 ${file.name} 失败:`, err);
			}
		}

		new Notice(
			`✅ 批量同步完成: ${created} 新增, ${updated} 更新, ${skipped} 跳过, ${errors} 失败`,
			5000
		);
	}

	updateStatusBar(file: TFile, status: string) {
		if (this.statusBarItemEl) {
			const cache = this.app.metadataCache.getFileCache(file);
			const postName = cache?.frontmatter?.["halo_post_name"];
			if (postName) {
				this.statusBarItemEl.setText(`📰 Halo: ${status}`);
			}
		}
	}

	async loadSettings() {
		this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
	}

	async saveSettings() {
		await this.saveData(this.settings);
		this.initClient();
	}
}

// ==================== 设置面板 ====================

class HaloSyncSettingTab extends PluginSettingTab {
	plugin: HaloObsidianSyncPlugin;

	constructor(app: App, plugin: HaloObsidianSyncPlugin) {
		super(app, plugin);
		this.plugin = plugin;
	}

	display() {
		const { containerEl } = this;
		containerEl.empty();

		containerEl.createEl("h2", { text: "Halo Obsidian Sync 设置" });

		new Setting(containerEl)
			.setName("Halo 博客地址")
			.setDesc("你的 Halo 2.x 博客地址，如 https://blog.example.com")
			.addText((text) =>
				text
					.setPlaceholder("https://blog.example.com")
					.setValue(this.plugin.settings.haloBaseUrl)
					.onChange(async (value) => {
						this.plugin.settings.haloBaseUrl = value.trim();
						await this.plugin.saveSettings();
					})
			);

		new Setting(containerEl)
			.setName("Personal Access Token")
			.setDesc("在 Halo 后台「个人中心 → 个人令牌」生成的 PAT Token")
			.addText((text) => {
				text.inputEl.type = "password";
				text
					.setPlaceholder("***")
					.setValue(this.plugin.settings.haloPatToken)
					.onChange(async (value) => {
						this.plugin.settings.haloPatToken = value.trim();
						await this.plugin.saveSettings();
					});
			});

		new Setting(containerEl)
			.setName("默认可见性")
			.setDesc("文章发布后的默认可见性")
			.addDropdown((dropdown) =>
				dropdown
					.addOption("PUBLIC", "公开")
					.addOption("PRIVATE", "私密")
					.setValue(this.plugin.settings.defaultVisible)
					.onChange(async (value) => {
						this.plugin.settings.defaultVisible = value;
						await this.plugin.saveSettings();
					})
			);

		new Setting(containerEl)
			.setName("自动发布")
			.setDesc("同步后是否自动发布文章（不打开则保存为草稿）")
			.addToggle((toggle) =>
				toggle
					.setValue(this.plugin.settings.autoPublish)
					.onChange(async (value) => {
						this.plugin.settings.autoPublish = value;
						await this.plugin.saveSettings();
					})
			);

		new Setting(containerEl)
			.setName("显示状态栏")
			.setDesc("在底部状态栏显示 Halo 同步状态")
			.addToggle((toggle) =>
				toggle
					.setValue(this.plugin.settings.showStatusBar)
					.onChange(async (value) => {
						this.plugin.settings.showStatusBar = value;
						await this.plugin.saveSettings();
					})
			);

		// 测试连接按钮
		new Setting(containerEl)
			.setName("测试连接")
			.setDesc("测试 Halo API 是否可正常连接")
			.addButton((btn) =>
				btn
					.setButtonText("测试")
					.setCta()
					.onClick(async () => {
						if (!this.plugin.settings.haloBaseUrl || !this.plugin.settings.haloPatToken) {
							new Notice("[错误] 请先填写地址和 Token", 4000);
							return;
						}
						btn.setDisabled(true);
						btn.setButtonText("测试中...");
						try {
							const client = new HaloApiClient(
								this.plugin.settings.haloBaseUrl,
								this.plugin.settings.haloPatToken
							);
							await client.listPosts(0, 1);
							new Notice("✅ 连接成功！Halo API 可正常访问", 4000);
						} catch (err: any) {
							new Notice(`❌ 连接失败: ${err.message || err}`, 5000);
						} finally {
							btn.setDisabled(false);
							btn.setButtonText("测试");
						}
					})
			);
	}
}
