"""
历史入口：曾与 ``make_analysis_zip.py`` 并列的宽口径打包脚本。

现行唯一推荐：**干净分析/交付包**请使用 ``python scripts/make_analysis_zip.py``
（输出 ``_local/exports/project_analysis_clean.zip``）。
本模块改为直接委托 ``make_analysis_zip.main``，避免再次生成含冗余/敏感路径习惯的历史包。
"""

from __future__ import annotations

from make_analysis_zip import main

if __name__ == "__main__":
    raise SystemExit(main())
