var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// main.ts
var main_exports = {};
__export(main_exports, {
  default: () => HaloObsidianSyncPlugin
});
module.exports = __toCommonJS(main_exports);
var import_obsidian = require("obsidian");
var DEFAULT_SETTINGS = {
  haloBaseUrl: "",
  haloPatToken: "",
  defaultVisible: "PUBLIC",
  autoPublish: true,
  showStatusBar: true
};
var HaloApiClient = class {
  constructor(baseUrl, token) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
  }
  async request(method, path, body, headers) {
    const url = `${this.baseUrl}${path}`;
    const reqHeaders = {
      "Authorization": `Bearer ${this.token}`,
      "Accept": "application/json",
      ...headers
    };
    if (body && typeof body === "object" && !(body instanceof FormData) && !(body instanceof Uint8Array)) {
      reqHeaders["Content-Type"] = "application/json";
    }
    try {
      const resp = await (0, import_obsidian.requestUrl)({
        url,
        method,
        headers: reqHeaders,
        body: body ? typeof body === "string" ? body : JSON.stringify(body) : void 0
      });
      if (resp.status >= 400) {
        throw new Error(`HTTP ${resp.status}: ${resp.text || ""}`);
      }
      return resp.json;
    } catch (err) {
      if (err.status === 401) {
        throw new Error("\u8BA4\u8BC1\u5931\u8D25\uFF1A\u8BF7\u68C0\u67E5 Halo Personal Access Token \u662F\u5426\u6709\u6548");
      }
      throw new Error(`Halo API \u9519\u8BEF: ${err.message || err}`);
    }
  }
  async listPosts(page = 0, size = 20, keyword) {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    if (keyword) params.append("keyword", keyword);
    return this.request("GET", `/apis/api.console.halo.run/v1alpha1/posts?${params.toString()}`);
  }
  async getPost(name) {
    return this.request("GET", `/apis/api.console.halo.run/v1alpha1/posts/${name}`);
  }
  async createPost(postBody) {
    return this.request("POST", "/apis/api.console.halo.run/v1alpha1/posts", postBody);
  }
  async updatePost(name, postBody) {
    return this.request("PUT", `/apis/api.console.halo.run/v1alpha1/posts/${name}`, postBody);
  }
  async publishPost(name) {
    return this.request("PUT", `/apis/api.console.halo.run/v1alpha1/posts/${name}/publish`);
  }
  async unpublishPost(name) {
    return this.request("PUT", `/apis/api.console.halo.run/v1alpha1/posts/${name}/unpublish`);
  }
  async uploadAttachment(fileData, filename, mimeType) {
    const boundary = "----FormBoundary" + Math.random().toString(36).slice(2);
    const encoder = new TextEncoder();
    const pre = encoder.encode(
      `--${boundary}\r
Content-Disposition: form-data; name="file"; filename="${filename}"\r
Content-Type: ${mimeType}\r
\r
`
    );
    const post = encoder.encode(`\r
--${boundary}--\r
`);
    const body = new Uint8Array(pre.length + fileData.byteLength + post.length);
    body.set(pre, 0);
    body.set(new Uint8Array(fileData), pre.length);
    body.set(post, pre.length + fileData.byteLength);
    const url = `${this.baseUrl}/apis/api.core.halo.run/v1alpha1/attachments`;
    try {
      const resp = await (0, import_obsidian.requestUrl)({
        url,
        method: "POST",
        headers: {
          "Authorization": `Bearer ${this.token}`,
          "Content-Type": `multipart/form-data; boundary=${boundary}`
        },
        body: body.buffer
      });
      if (resp.status >= 400) {
        throw new Error(`HTTP ${resp.status}: ${resp.text || ""}`);
      }
      return resp.json;
    } catch (err) {
      throw new Error(`\u9644\u4EF6\u4E0A\u4F20\u5931\u8D25: ${err.message || err}`);
    }
  }
  async listTags(page = 0, size = 50) {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    return this.request("GET", `/apis/api.console.halo.run/v1alpha1/tags?${params.toString()}`);
  }
  async listCategories(page = 0, size = 50) {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    return this.request("GET", `/apis/api.console.halo.run/v1alpha1/categories?${params.toString()}`);
  }
};
var SyncEngine = class {
  constructor(app, client, settings) {
    this.app = app;
    this.client = client;
    this.settings = settings;
  }
  /**
   * 解析笔记元数据
   */
  async parseNote(file) {
    const cache = this.app.metadataCache.getFileCache(file);
    const meta = (cache == null ? void 0 : cache.frontmatter) || {};
    const content = await this.app.vault.cachedRead(file) || "";
    return {
      meta,
      content,
      shouldSync: !!meta["halo_sync"]
    };
  }
  /**
   * 提取正文中的图片引用
   */
  extractImages(content) {
    const images = [];
    const wikiRegex = /!?\[\[([^\]|]+)(?:\|[^\]]*)?\]\]/g;
    let match;
    while ((match = wikiRegex.exec(content)) !== null) {
      images.push(match[1].trim());
    }
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
  resolveImagePath(imageRef, noteDir) {
    const vault = this.app.vault;
    const candidates = [
      `${noteDir}/${imageRef}`,
      imageRef,
      `attachments/${imageRef}`,
      `Images/${imageRef}`,
      `images/${imageRef}`
    ];
    for (const cand of candidates) {
      const file = vault.getAbstractFileByPath(cand);
      if (file && file instanceof import_obsidian.TFile) {
        return cand;
      }
    }
    return null;
  }
  /**
   * 处理附件上传，替换正文中的图片链接
   */
  async processAttachments(content, noteDir) {
    var _a, _b;
    const images = this.extractImages(content);
    let processed = content;
    for (const imgRef of images) {
      const resolvedPath = this.resolveImagePath(imgRef, noteDir);
      if (!resolvedPath) {
        console.warn(`[\u8B66\u544A] \u627E\u4E0D\u5230\u56FE\u7247: ${imgRef}`);
        continue;
      }
      const file = this.app.vault.getAbstractFileByPath(resolvedPath);
      if (!file || !(file instanceof import_obsidian.TFile)) continue;
      try {
        const binary = await this.app.vault.readBinary(file);
        const mime = this.guessMime(file.extension);
        const att = await this.client.uploadAttachment(binary, file.name, mime);
        const permalink = ((_a = att == null ? void 0 : att.spec) == null ? void 0 : _a.permalink) || ((_b = att == null ? void 0 : att.spec) == null ? void 0 : _b.url);
        if (permalink) {
          processed = this.replaceImageRef(processed, imgRef, permalink);
        }
      } catch (err) {
        console.warn(`[\u8B66\u544A] \u4E0A\u4F20\u56FE\u7247 ${imgRef} \u5931\u8D25:`, err);
      }
    }
    return processed;
  }
  replaceImageRef(content, oldRef, newUrl) {
    content = content.replace(
      new RegExp(`!?\\[\\[${this.escapeRegExp(oldRef)}(\\|[^\\]]*)?\\]\\]`, "g"),
      `![${oldRef.split("/").pop() || oldRef}](${newUrl})`
    );
    content = content.replace(
      new RegExp(`!\\[([^\\]]*)\\]\\(${this.escapeRegExp(oldRef)}\\)`, "g"),
      `![$1](${newUrl})`
    );
    return content;
  }
  escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }
  guessMime(ext) {
    const map = {
      png: "image/png",
      jpg: "image/jpeg",
      jpeg: "image/jpeg",
      gif: "image/gif",
      svg: "image/svg+xml",
      webp: "image/webp",
      mp4: "video/mp4",
      pdf: "application/pdf",
      zip: "application/zip"
    };
    return map[ext.toLowerCase()] || "application/octet-stream";
  }
  /**
   * 构建 Halo Post 对象
   */
  buildPostBody(meta, content, visible) {
    const title = meta["title"] || "";
    const slug = meta["slug"] || this.toSlug(title);
    const tags = this.normalizeList(meta["tags"]);
    const categories = this.normalizeList(meta["categories"]);
    const excerpt = meta["excerpt"] || meta["description"] || "";
    const body = {
      spec: {
        title,
        slug,
        content,
        visible
      },
      metadata: {}
    };
    if (tags.length > 0) body.spec.tags = tags;
    if (categories.length > 0) body.spec.categories = categories;
    if (excerpt) {
      body.spec.excerpt = {
        autoGenerate: false,
        raw: excerpt
      };
    }
    return body;
  }
  normalizeList(val) {
    if (!val) return [];
    if (Array.isArray(val)) return val.map(String);
    if (typeof val === "string") return val.split(",").map((s) => s.trim()).filter(Boolean);
    return [];
  }
  toSlug(text) {
    return text.replace(/[^\u4e00-\u9fa5a-zA-Z0-9_-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 100);
  }
  /**
   * 主同步函数
   */
  async syncNote(file, force = false) {
    var _a, _b, _c, _d;
    const { meta, content, shouldSync } = await this.parseNote(file);
    if (!shouldSync) {
      return { status: "skipped", message: "halo_sync \u672A\u8BBE\u7F6E\u4E3A true\uFF0C\u8DF3\u8FC7" };
    }
    const postName = meta["halo_post_name"];
    const lastSync = meta["halo_last_sync"];
    if (!force && postName && lastSync) {
      const mtime = file.stat.mtime;
      const syncTime = new Date(lastSync).getTime();
      if (!isNaN(syncTime) && mtime <= syncTime) {
        return { status: "skipped", postName, message: "\u6587\u4EF6\u672A\u53D8\u66F4\uFF0C\u8DF3\u8FC7" };
      }
    }
    const noteDir = ((_a = file.parent) == null ? void 0 : _a.path) || "";
    let processedContent;
    try {
      processedContent = await this.processAttachments(content, noteDir);
    } catch (err) {
      return { status: "error", postName, message: `\u9644\u4EF6\u5904\u7406\u5931\u8D25: ${err}` };
    }
    const postBody = this.buildPostBody(meta, processedContent, this.settings.defaultVisible);
    let status;
    let resultPostName;
    try {
      if (postName) {
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
            postBody.metadata = {};
            const created = await this.client.createPost(postBody);
            resultPostName = (_b = created.metadata) == null ? void 0 : _b.name;
            if (meta["halo_status"] === "published") {
              await this.client.publishPost(resultPostName);
            }
            status = "created";
          }
        } catch (err) {
          postBody.metadata = {};
          const created = await this.client.createPost(postBody);
          resultPostName = (_c = created.metadata) == null ? void 0 : _c.name;
          if (meta["halo_status"] === "published") {
            await this.client.publishPost(resultPostName);
          }
          status = "created";
        }
      } else {
        postBody.metadata = {};
        const created = await this.client.createPost(postBody);
        resultPostName = (_d = created.metadata) == null ? void 0 : _d.name;
        if (meta["halo_status"] === "published" || this.settings.autoPublish) {
          await this.client.publishPost(resultPostName);
        }
        status = "created";
      }
    } catch (err) {
      return { status: "error", postName: resultPostName, message: `Halo API \u9519\u8BEF: ${err.message || err}` };
    }
    const now = (/* @__PURE__ */ new Date()).toISOString();
    await this.updateFrontmatter(file, {
      "halo_post_name": resultPostName,
      "halo_status": meta["halo_status"] || (this.settings.autoPublish ? "published" : "draft"),
      "halo_last_sync": now
    });
    return { status, postName: resultPostName, message: `${status}: ${meta["title"] || file.name}` };
  }
  async updateFrontmatter(file, updates) {
    await this.app.fileManager.processFrontMatter(file, (frontmatter) => {
      for (const [key, value] of Object.entries(updates)) {
        frontmatter[key] = value;
      }
    });
  }
};
var HaloObsidianSyncPlugin = class extends import_obsidian.Plugin {
  constructor() {
    super(...arguments);
    this.statusBarItemEl = null;
    this.client = null;
    this.engine = null;
  }
  async onload() {
    await this.loadSettings();
    this.initClient();
    this.addSettingTab(new HaloSyncSettingTab(this.app, this));
    this.addCommand({
      id: "halo-sync-current-note",
      name: "\u540C\u6B65\u5F53\u524D\u7B14\u8BB0\u5230 Halo",
      editorCallback: (editor, ctx) => {
        const file = ctx.file;
        if (file) {
          this.syncCurrentNote(file);
        }
      }
    });
    this.addCommand({
      id: "halo-sync-force-current-note",
      name: "\u5F3A\u5236\u91CD\u65B0\u540C\u6B65\u5F53\u524D\u7B14\u8BB0\u5230 Halo",
      editorCallback: (editor, ctx) => {
        const file = ctx.file;
        if (file) {
          this.syncCurrentNote(file, true);
        }
      }
    });
    this.addCommand({
      id: "halo-sync-all-notes",
      name: "\u6279\u91CF\u540C\u6B65\u6240\u6709\u6807\u8BB0\u7684\u7B14\u8BB0\u5230 Halo",
      callback: () => {
        this.syncAllNotes();
      }
    });
    this.registerEvent(
      this.app.workspace.on("file-menu", (menu, file) => {
        if (file instanceof import_obsidian.TFile && file.extension === "md") {
          menu.addItem((item) => {
            item.setTitle("\u540C\u6B65\u5230 Halo").setIcon("upload").onClick(() => {
              this.syncCurrentNote(file);
            });
          });
        }
      })
    );
    if (this.settings.showStatusBar) {
      this.statusBarItemEl = this.addStatusBarItem();
      this.statusBarItemEl.setText("\u{1F4F0} Halo");
      this.statusBarItemEl.addClass("halo-sync-status-bar");
      this.statusBarItemEl.onClickEvent(() => {
        const activeFile = this.app.workspace.getActiveFile();
        if (activeFile) {
          this.syncCurrentNote(activeFile);
        }
      });
    }
    console.log("[Halo Obsidian Sync] \u63D2\u4EF6\u5DF2\u52A0\u8F7D");
  }
  onunload() {
    console.log("[Halo Obsidian Sync] \u63D2\u4EF6\u5DF2\u5378\u8F7D");
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
  async syncCurrentNote(file, force = false) {
    if (!this.engine) {
      new import_obsidian.Notice("[\u9519\u8BEF] Halo \u914D\u7F6E\u672A\u5B8C\u6210\uFF0C\u8BF7\u5148\u5728\u8BBE\u7F6E\u4E2D\u586B\u5199\u5730\u5740\u548C Token", 5e3);
      return;
    }
    new import_obsidian.Notice(`\u{1F504} \u6B63\u5728\u540C\u6B65: ${file.name}...`);
    try {
      const result = await this.engine.syncNote(file, force);
      if (result.status === "created" || result.status === "updated") {
        new import_obsidian.Notice(`\u2705 \u540C\u6B65\u6210\u529F: ${result.message}`, 4e3);
        this.updateStatusBar(file, result.status);
      } else if (result.status === "skipped") {
        new import_obsidian.Notice(`\u23ED\uFE0F \u5DF2\u8DF3\u8FC7: ${result.message}`, 3e3);
      } else {
        new import_obsidian.Notice(`\u274C \u540C\u6B65\u5931\u8D25: ${result.message}`, 5e3);
      }
    } catch (err) {
      new import_obsidian.Notice(`\u274C \u540C\u6B65\u5F02\u5E38: ${err.message || err}`, 5e3);
      console.error("[Halo Sync] \u540C\u6B65\u5F02\u5E38:", err);
    }
  }
  async syncAllNotes() {
    var _a;
    if (!this.engine) {
      new import_obsidian.Notice("[\u9519\u8BEF] Halo \u914D\u7F6E\u672A\u5B8C\u6210", 5e3);
      return;
    }
    const files = this.app.vault.getMarkdownFiles();
    const syncFiles = [];
    for (const file of files) {
      const cache = this.app.metadataCache.getFileCache(file);
      if (((_a = cache == null ? void 0 : cache.frontmatter) == null ? void 0 : _a["halo_sync"]) === true) {
        syncFiles.push(file);
      }
    }
    if (syncFiles.length === 0) {
      new import_obsidian.Notice("\u6CA1\u6709\u627E\u5230\u6807\u8BB0\u4E86 halo_sync: true \u7684\u7B14\u8BB0", 3e3);
      return;
    }
    new import_obsidian.Notice(`\u{1F504} \u5F00\u59CB\u6279\u91CF\u540C\u6B65 ${syncFiles.length} \u7BC7\u7B14\u8BB0...`);
    let created = 0, updated = 0, skipped = 0, errors = 0;
    for (const file of syncFiles) {
      try {
        const result = await this.engine.syncNote(file);
        if (result.status === "created") created++;
        else if (result.status === "updated") updated++;
        else if (result.status === "skipped") skipped++;
        else errors++;
      } catch (err) {
        errors++;
        console.error(`[Halo Sync] \u540C\u6B65 ${file.name} \u5931\u8D25:`, err);
      }
    }
    new import_obsidian.Notice(
      `\u2705 \u6279\u91CF\u540C\u6B65\u5B8C\u6210: ${created} \u65B0\u589E, ${updated} \u66F4\u65B0, ${skipped} \u8DF3\u8FC7, ${errors} \u5931\u8D25`,
      5e3
    );
  }
  updateStatusBar(file, status) {
    var _a;
    if (this.statusBarItemEl) {
      const cache = this.app.metadataCache.getFileCache(file);
      const postName = (_a = cache == null ? void 0 : cache.frontmatter) == null ? void 0 : _a["halo_post_name"];
      if (postName) {
        this.statusBarItemEl.setText(`\u{1F4F0} Halo: ${status}`);
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
};
var HaloSyncSettingTab = class extends import_obsidian.PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }
  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Halo Obsidian Sync \u8BBE\u7F6E" });
    new import_obsidian.Setting(containerEl).setName("Halo \u535A\u5BA2\u5730\u5740").setDesc("\u4F60\u7684 Halo 2.x \u535A\u5BA2\u5730\u5740\uFF0C\u5982 https://blog.example.com").addText(
      (text) => text.setPlaceholder("https://blog.example.com").setValue(this.plugin.settings.haloBaseUrl).onChange(async (value) => {
        this.plugin.settings.haloBaseUrl = value.trim();
        await this.plugin.saveSettings();
      })
    );
    new import_obsidian.Setting(containerEl).setName("Personal Access Token").setDesc("\u5728 Halo \u540E\u53F0\u300C\u4E2A\u4EBA\u4E2D\u5FC3 \u2192 \u4E2A\u4EBA\u4EE4\u724C\u300D\u751F\u6210\u7684 PAT Token").addText((text) => {
      text.inputEl.type = "password";
      text.setPlaceholder("***").setValue(this.plugin.settings.haloPatToken).onChange(async (value) => {
        this.plugin.settings.haloPatToken = value.trim();
        await this.plugin.saveSettings();
      });
    });
    new import_obsidian.Setting(containerEl).setName("\u9ED8\u8BA4\u53EF\u89C1\u6027").setDesc("\u6587\u7AE0\u53D1\u5E03\u540E\u7684\u9ED8\u8BA4\u53EF\u89C1\u6027").addDropdown(
      (dropdown) => dropdown.addOption("PUBLIC", "\u516C\u5F00").addOption("PRIVATE", "\u79C1\u5BC6").setValue(this.plugin.settings.defaultVisible).onChange(async (value) => {
        this.plugin.settings.defaultVisible = value;
        await this.plugin.saveSettings();
      })
    );
    new import_obsidian.Setting(containerEl).setName("\u81EA\u52A8\u53D1\u5E03").setDesc("\u540C\u6B65\u540E\u662F\u5426\u81EA\u52A8\u53D1\u5E03\u6587\u7AE0\uFF08\u4E0D\u6253\u5F00\u5219\u4FDD\u5B58\u4E3A\u8349\u7A3F\uFF09").addToggle(
      (toggle) => toggle.setValue(this.plugin.settings.autoPublish).onChange(async (value) => {
        this.plugin.settings.autoPublish = value;
        await this.plugin.saveSettings();
      })
    );
    new import_obsidian.Setting(containerEl).setName("\u663E\u793A\u72B6\u6001\u680F").setDesc("\u5728\u5E95\u90E8\u72B6\u6001\u680F\u663E\u793A Halo \u540C\u6B65\u72B6\u6001").addToggle(
      (toggle) => toggle.setValue(this.plugin.settings.showStatusBar).onChange(async (value) => {
        this.plugin.settings.showStatusBar = value;
        await this.plugin.saveSettings();
      })
    );
    new import_obsidian.Setting(containerEl).setName("\u6D4B\u8BD5\u8FDE\u63A5").setDesc("\u6D4B\u8BD5 Halo API \u662F\u5426\u53EF\u6B63\u5E38\u8FDE\u63A5").addButton(
      (btn) => btn.setButtonText("\u6D4B\u8BD5").setCta().onClick(async () => {
        if (!this.plugin.settings.haloBaseUrl || !this.plugin.settings.haloPatToken) {
          new import_obsidian.Notice("[\u9519\u8BEF] \u8BF7\u5148\u586B\u5199\u5730\u5740\u548C Token", 4e3);
          return;
        }
        btn.setDisabled(true);
        btn.setButtonText("\u6D4B\u8BD5\u4E2D...");
        try {
          const client = new HaloApiClient(
            this.plugin.settings.haloBaseUrl,
            this.plugin.settings.haloPatToken
          );
          await client.listPosts(0, 1);
          new import_obsidian.Notice("\u2705 \u8FDE\u63A5\u6210\u529F\uFF01Halo API \u53EF\u6B63\u5E38\u8BBF\u95EE", 4e3);
        } catch (err) {
          new import_obsidian.Notice(`\u274C \u8FDE\u63A5\u5931\u8D25: ${err.message || err}`, 5e3);
        } finally {
          btn.setDisabled(false);
          btn.setButtonText("\u6D4B\u8BD5");
        }
      })
    );
  }
};
