#!/usr/bin/env python3
"""
把官方 dsh-nexttavern 发布包改造成能跑在指定 dsh 宿主版本上的兼容包。

原理：插件几乎不直接 import 宿主（只有 cordis / cordis-plugin-loader /
dsh-atomic-write 三个），其余全靠 Cordis 服务注入，所以跨宿主版本适配
不需要改代码，只要把安装期的版本约束（peerDependencies）重映射即可。

用法：
    python patch.py                      # 自动探测本机 dsh 宿主版本
    python patch.py --dsh-version 0.2.1-alpha.1
    python patch.py --plugin-version 0.2.9 --out ./dist

产出：一个 tgz，可直接 dsh plugin add file:<路径>
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

PKG_NAME = "dsh-nexttavern"
REGISTRY = "https://registry.npmjs.org"

# 插件原版锁定的宿主版本 -> 需要替换为探测到的宿主真实版本
LEGACY_VERSIONS = {
    "0.1.7-rc.2",
    "4.0.4",          # cordis
    "1.0.9",          # cordis-plugin-include
    "1.0.5",          # cordis-plugin-loader
    "3.18.4",         # schemastery
}


def find_dsh_root() -> str | None:
    """定位全局安装的 @deepseek-ai/dsh 包目录。"""
    dsh = shutil.which("dsh")
    candidates = []
    if dsh:
        # npm 的 shim 指向 node_modules/<pkg>/<bin>
        p = os.path.realpath(dsh)
        candidates.append(p)
        idx = p.replace("\\", "/").find("/node_modules/")
        if idx > 0:
            candidates.append(p[: idx + len("/node_modules/")] + "@deepseek-ai/dsh")
    candidates += [
        os.path.expandvars(r"%APPDATA%\npm\node_modules\@deepseek-ai\dsh"),
        "/usr/lib/node_modules/@deepseek-ai/dsh",
        "/usr/local/lib/node_modules/@deepseek-ai/dsh",
    ]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "package.json")):
            try:
                name = json.load(open(os.path.join(c, "package.json"), encoding="utf-8")).get("name")
            except Exception:
                continue
            if name == "@deepseek-ai/dsh":
                return c
    return None


def probe_host_versions(dsh_root: str) -> tuple[str, dict[str, str]]:
    """读取宿主实际提供的 @deepseek-ai/* 包版本。"""
    with open(os.path.join(dsh_root, "package.json"), encoding="utf-8") as f:
        dsh_version = json.load(f)["version"]
    nested = os.path.join(dsh_root, "node_modules", "@deepseek-ai")
    versions: dict[str, str] = {}
    for manifest in glob.glob(os.path.join(nested, "*", "package.json")):
        try:
            d = json.load(open(manifest, encoding="utf-8"))
        except Exception:
            continue
        if d.get("name"):
            versions[d["name"]] = d.get("version", "")
    return dsh_version, versions


def fetch_tarball(version: str, dest: str) -> str:
    url = f"{REGISTRY}/{PKG_NAME}/-/{PKG_NAME}-{version}.tgz"
    print(f"下载 {url}")
    with urllib.request.urlopen(url, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def patch_manifest(path: str, host: dict[str, str]) -> tuple[int, list[str]]:
    with open(path, encoding="utf-8") as f:
        pkg = json.load(f)
    peers = pkg.get("peerDependencies", {})
    changed, missing = 0, []
    for name, old in list(peers.items()):
        if name.startswith("dsh-nexttavern-"):
            continue  # 插件自有包，不动
        if old not in LEGACY_VERSIONS:
            continue
        new = host.get(name)
        if not new:
            missing.append(name)
            continue
        peers[name] = new
        changed += 1
    # 宿主已移除、且插件代码从未 import 的包 -> 降级为可选
    optional = []
    for name in missing:
        pkg.setdefault("peerDependenciesMeta", {})[name] = {"optional": True}
        optional.append(name)
        print(f"  ! {name} 在宿主中不存在，已标记为 optional")
    if changed or optional:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pkg, f, ensure_ascii=False, indent=2)
    return changed, missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsh-version", help="目标 dsh 宿主版本（默认自动探测）")
    ap.add_argument("--plugin-version", default="0.2.9", help="插件版本，默认 0.2.9")
    ap.add_argument("--out", default=".", help="输出目录")
    ap.add_argument("--keep", action="store_true", help="保留解包产物")
    args = ap.parse_args()

    dsh_root = find_dsh_root()
    if not dsh_root:
        print("错误：找不到全局安装的 @deepseek-ai/dsh，请先安装 dsh。", file=sys.stderr)
        return 1
    dsh_version, host = probe_host_versions(dsh_root)
    target = args.dsh_version or dsh_version
    print(f"宿主目录: {dsh_root}")
    print(f"宿主版本: {dsh_version}（目标 {target}），宿主提供 {len(host)} 个 @deepseek-ai/* 包")

    work = tempfile.mkdtemp(prefix="dsh-tav-")
    try:
        tgz = fetch_tarball(args.plugin_version, os.path.join(work, "orig.tgz"))
        with tarfile.open(tgz) as t:
            t.extractall(os.path.join(work, "x"))
        root = os.path.join(work, "x", "package")
        if not os.path.isdir(root):
            print("错误：tarball 结构异常，未找到 package/ 目录", file=sys.stderr)
            return 1

        manifest = os.path.join(root, "package.json")
        before = json.load(open(manifest, encoding="utf-8"))
        if before.get("version") != args.plugin_version:
            print(f"注意：manifest 版本 {before.get('version')} 与预期不同")

        n, missing = patch_manifest(manifest, host)
        after = json.load(open(manifest, encoding="utf-8"))
        # 版本号必须保持不变：插件会用它和 nexttavern.dependencies.json 做自校验
        assert after["version"] == before["version"], "版本号被改动，会导致 inventory 校验失败"
        print(f"已重映射 {n} 条 peer；缺失 {len(missing)} 个包已标为 optional")

        os.makedirs(args.out, exist_ok=True)
        out_name = f"{PKG_NAME}-{args.plugin_version}-{target}.tgz"
        out_path = os.path.join(args.out, out_name)
        with tarfile.open(out_path, "w:gz") as t:
            t.add(root, arcname="package")
        sha = hashlib.sha256(open(out_path, "rb").read()).hexdigest()
        size = os.path.getsize(out_path) / 1048576
        print(f"\n完成: {os.path.abspath(out_path)}")
        print(f"  {size:.1f} MB  sha256={sha[:16]}…")
        if args.keep:
            print(f"  解包产物: {root}")
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
