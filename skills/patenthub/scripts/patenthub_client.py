#!/usr/bin/env python3
"""
PatentHub API client for DeepAgents Skill.
Zero-dependency: uses only stdlib.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.patenthub.cn"

ERROR_CODES = {
    200: "响应成功",
    201: "token为空",
    202: "非法token",
    203: "响应异常",
    204: "ip被拒绝访问",
    205: "参数值为空",
    206: "没有找到对应数据",
    207: "该接口当天访问次数已经用尽",
    208: "没有访问权限",
    209: "版本号为空",
    210: "参数错误",
    211: "该等级接口当年专利总数量已经用尽",
    212: "分析维度为空",
    213: "分析维度不存在",
    214: "TOKEN类型错误",
    215: "异常访问，被终止，请查看接口规范（通常因为专利ID无效或已过期，请重新通过搜索接口获取）",
    216: "获取年费数据异常",
    217: "访问说明书附图数量超过专利总量的3倍限制",
    218: "搜索、引用、相似接口总调用量超过了每日调用量的100倍限制",
}


def get_token() -> str:
    token = os.environ.get("PATENTHUB_TOKEN", "")
    if not token:
        print(
            json.dumps(
                {
                    "error": "Missing PATENTHUB_TOKEN environment variable.",
                    "code": None,
                }
            ),
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def api_get(endpoint: str, params: dict) -> dict:
    token = get_token()
    # Prefer token in query string for broader compatibility with PatentHub
    params = {**params, "t": token, "v": "1"}
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}{endpoint}?{query}"
    try:
        req = urllib.request.Request(url, method="GET", headers={
            "User-Agent": "Mozilla/5.0 (PatentHub-Skill/1.0)",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
        if isinstance(data, dict) and not data.get("success", True):
            code = data.get("code", "unknown")
            msg = data.get("message", data.get("msg", "API returned failure"))
            return {
                "success": False,
                "code": code,
                "error": msg,
                "raw": data,
            }
        return {"success": True, "data": data}
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "code": e.code,
            "error": f"HTTP error: {e.code} {e.reason}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def _print_error(result: dict):
    code = result.get("code")
    msg = result.get("error", "Unknown error")
    desc = ERROR_CODES.get(code, "未知错误")
    print(json.dumps({
        "error": msg,
        "description": desc,
        "code": code,
    }, ensure_ascii=False, indent=2))


def cmd_search(args):
    params = {"q": args.query}
    if args.page is not None:
        params["p"] = args.page
    if args.page_size is not None:
        params["ps"] = args.page_size
    if args.data_scope is not None:
        params["ds"] = args.data_scope
    if args.sort is not None:
        params["s"] = args.sort
    if args.highlight:
        params["hl"] = 1
    result = api_get("/api/s", params)
    if not result["success"]:
        _print_error(result)
        return
    data = result["data"]
    print(json.dumps({
        "total": data.get("total"),
        "page": data.get("page"),
        "totalPages": data.get("totalPages"),
        "patents": data.get("patents", []),
    }, ensure_ascii=False, indent=2))


def cmd_base(args):
    result = api_get("/api/patent/base", {"id": args.id})
    if not result["success"]:
        _print_error(result)
        return
    data = result["data"]
    print(json.dumps({
        "patent": data.get("patent"),
    }, ensure_ascii=False, indent=2))


def cmd_claims(args):
    result = api_get("/api/patent/claims", {"id": args.id})
    if not result["success"]:
        _print_error(result)
        return
    data = result["data"]
    patent = data.get("patent")
    if patent and isinstance(patent, dict) and "claims" in patent:
        patent = {**patent, "claims": patent["claims"].replace("<br/>", "\n")}
    print(json.dumps({
        "patent": patent,
    }, ensure_ascii=False, indent=2))


def cmd_desc(args):
    result = api_get("/api/patent/desc", {"id": args.id})
    if not result["success"]:
        _print_error(result)
        return
    data = result["data"]
    patent = data.get("patent")
    if patent and isinstance(patent, dict) and "description" in patent:
        patent = {**patent, "description": patent["description"].replace("<br/>", "\n")}
    print(json.dumps({
        "patent": patent,
    }, ensure_ascii=False, indent=2))


def cmd_tx(args):
    result = api_get("/api/patent/tx", {"id": args.id})
    if not result["success"]:
        _print_error(result)
        return
    data = result["data"]
    print(json.dumps({
        "transactions": data.get("transactions", []),
    }, ensure_ascii=False, indent=2))


def cmd_citing(args):
    result = api_get("/api/patent/citing", {"id": args.id})
    if not result["success"]:
        _print_error(result)
        return
    data = result["data"]
    print(json.dumps({
        "citedList": data.get("citedList", []),
        "patentXref": data.get("patentXref", []),
        "noPatentXref": data.get("noPatentXref", []),
    }, ensure_ascii=False, indent=2))


def cmd_like(args):
    result = api_get("/api/patent/like", {"id": args.id})
    if not result["success"]:
        _print_error(result)
        return
    data = result["data"]
    print(json.dumps({
        "patentLikeList": data.get("patentLikeList", []),
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="PatentHub API CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_search = subparsers.add_parser("search", help="Search patents")
    p_search.add_argument("--query", "-q", required=True, help="Search query")
    p_search.add_argument("--page", "-p", type=int, help="Page number (default 1, max 100)")
    p_search.add_argument("--page-size", "-ps", type=int, help="Page size (default 10, max 50)")
    p_search.add_argument("--data-scope", "-ds", choices=["cn", "all"], help="Data scope: cn or all (default cn)")
    p_search.add_argument("--sort", "-s", help="Sort field: relation, applicationDate, documentDate, rank. Prefix with ! for desc.")
    p_search.add_argument("--highlight", "-hl", action="store_true", help="Highlight results")
    p_search.set_defaults(func=cmd_search)

    p_base = subparsers.add_parser("base", help="Get patent base info")
    p_base.add_argument("--id", required=True, help="Patent ID")
    p_base.set_defaults(func=cmd_base)

    p_claims = subparsers.add_parser("claims", help="Get patent claims")
    p_claims.add_argument("--id", required=True, help="Patent ID")
    p_claims.set_defaults(func=cmd_claims)

    p_desc = subparsers.add_parser("desc", help="Get patent description")
    p_desc.add_argument("--id", required=True, help="Patent ID")
    p_desc.set_defaults(func=cmd_desc)

    p_tx = subparsers.add_parser("tx", help="Get patent legal info")
    p_tx.add_argument("--id", required=True, help="Patent ID")
    p_tx.set_defaults(func=cmd_tx)

    p_citing = subparsers.add_parser("citing", help="Get patent citations")
    p_citing.add_argument("--id", required=True, help="Patent ID")
    p_citing.set_defaults(func=cmd_citing)

    p_like = subparsers.add_parser("like", help="Get similar patents")
    p_like.add_argument("--id", required=True, help="Patent ID")
    p_like.set_defaults(func=cmd_like)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
