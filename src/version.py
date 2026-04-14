# -*- coding: utf-8 -*-
"""應用程式版本與 GitHub 倉庫（供「一鍵更新」與發行對照）。"""

# 發佈新版本時請一併更新此號碼，並在 GitHub 建立對應 tag / Release。
APP_VERSION = "1.13"

# 發佈到 GitHub 後請改成「使用者名稱/倉庫名稱」，例如 "octocat/Hello-World"。
# 留空則僅在偵測到 .git 時使用 git pull，不會查詢 GitHub API。
GITHUB_REPO: str = "paintcanorz-design/sponsor-tracker"
