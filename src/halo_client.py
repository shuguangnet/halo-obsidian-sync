"""
Halo 2.x REST API 客户端封装
支持: 文章 CRUD、发布、附件上传、标签/分类查询
"""
import time
import requests
import json
from typing import Optional, Dict, Any, List


class HaloClient:
    """
    Halo 2.x 博客客户端

    使用 Personal Access Token 认证:
      - Authorization: Bearer {token}
    """

    def __init__(self, base_url: str, token: str, timeout: int = 30, retry: int = 3):
        # 去掉末尾斜杠，确保路径等级的 URL
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.retry = retry
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """发送 HTTP 请求，带重试机制"""
        url = f"{self.base_url}{path}"
        last_err = None
        for attempt in range(self.retry):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
                # 401 时直接抛出
                if resp.status_code == 401:
                    raise HaloAuthError("Halo 认证失败，请检查 Personal Access Token 是否有效")
                # 2xx 或其他可接受状态码
                if resp.status_code >= 500:
                    raise HaloServerError(f"Halo 服务器错误 {resp.status_code}: {resp.text[:200]}")
                # 204 No Content 时返回空
                if resp.status_code == 204:
                    return {}
                return resp.json()
            except requests.exceptions.ConnectionError as e:
                last_err = e
                if attempt < self.retry - 1:
                    time.sleep(2 ** attempt)  # 指数退避
        raise HaloNetworkError(f"请求失败（重试 {self.retry} 次后）: {last_err}")

    # ------------------------------------------------------------------
    # 文章管理
    # ------------------------------------------------------------------

    def list_posts(self, page: int = 0, size: int = 20, keyword: str = None) -> Dict[str, Any]:
        """获取文章列表"""
        params = {"page": page, "size": size}
        if keyword:
            params["keyword"] = keyword
        return self._request("GET", "/apis/api.console.halo.run/v1alpha1/posts", params=params)

    def get_post(self, name: str) -> Dict[str, Any]:
        """获取单篇文章"""
        return self._request("GET", f"/apis/api.console.halo.run/v1alpha1/posts/{name}")

    def create_post(self, post_body: Dict[str, Any]) -> Dict[str, Any]:
        """创建草稿（未发布）"""
        return self._request("POST", "/apis/api.console.halo.run/v1alpha1/posts", json=post_body)

    def update_post(self, name: str, post_body: Dict[str, Any]) -> Dict[str, Any]:
        """更新草稿"""
        return self._request("PUT", f"/apis/api.console.halo.run/v1alpha1/posts/{name}", json=post_body)

    def publish_post(self, name: str) -> Dict[str, Any]:
        """发布文章（将草稿变为已发布）"""
        return self._request("PUT", f"/apis/api.console.halo.run/v1alpha1/posts/{name}/publish")

    def unpublish_post(self, name: str) -> Dict[str, Any]:
        """撤销发布"""
        return self._request("PUT", f"/apis/api.console.halo.run/v1alpha1/posts/{name}/unpublish")

    # ------------------------------------------------------------------
    # 附件管理
    # ------------------------------------------------------------------

    def upload_attachment(self, file_path: str, filename: str = None, group_name: str = None) -> Dict[str, Any]:
        """
        上传文件到 Halo 附件库
        返回包含 permalink 的附件对象
        """
        if not filename:
            filename = file_path.split("/")[-1]
        files = {
            "file": (filename, open(file_path, "rb"), self._guess_mime(file_path))
        }
        # 上传附件需要设为 multipart/form-data，先屏蔽 json 头
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/apis/api.core.halo.run/v1alpha1/attachments"
        data = {}
        if group_name:
            data["groupName"] = group_name
        try:
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        finally:
            # 确保文件句柄被关闭
            for _, fp in files.items():
                if hasattr(fp[1], "close"):
                    fp[1].close()

    def _guess_mime(self, path: str) -> str:
        """简单的 MIME 猜测"""
        suffix = path.lower().split(".")[-1] if "." in path else ""
        mapping = {
            "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp",
            "mp4": "video/mp4", "pdf": "application/pdf", "zip": "application/zip",
        }
        return mapping.get(suffix, "application/octet-stream")

    # ------------------------------------------------------------------
    # 标签 / 分类
    # ------------------------------------------------------------------

    def list_tags(self, page: int = 0, size: int = 50) -> Dict[str, Any]:
        return self._request("GET", "/apis/api.console.halo.run/v1alpha1/tags", params={"page": page, "size": size})

    def create_tag(self, tag_body: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/apis/api.console.halo.run/v1alpha1/tags", json=tag_body)

    def list_categories(self, page: int = 0, size: int = 50) -> Dict[str, Any]:
        return self._request("GET", "/apis/api.console.halo.run/v1alpha1/categories", params={"page": page, "size": size})

    def create_category(self, category_body: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/apis/api.console.halo.run/v1alpha1/categories", json=category_body)


class HaloError(Exception):
    """Halo 客户端基础异常"""
    pass

class HaloAuthError(HaloError):
    """认证失败"""
    pass

class HaloServerError(HaloError):
    """服务器错误"""
    pass

class HaloNetworkError(HaloError):
    """网络错误"""
    pass
