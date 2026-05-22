# PatentHub API 快速参考

## 基础信息

- **Base URL**: `https://www.patenthub.cn`
- **认证方式**: URL 参数 `token=<PATENTHUB_TOKEN>`
- **返回格式**: JSON

## 接口列表

### 1. 搜索接口

- **URL**: `/api/s`
- **方法**: GET
- **说明**: 专利全文检索，只支持返回前1000条记录。通过搜索接口获取的专利 `id` 在详情接口中有效时间为 **60分钟**，直接构造 `id` 访问详情接口可能返回 215 错误。
- **参数**:
  - `q` (string, 必填): 检索关键词或检索式
  - `t` (string, 必填): Token
  - `v` (string, 必填): 版本号，当前为 `1`
  - `ds` (string, 可选): 数据范围，`cn`（中国，默认）或 `all`（全球）
  - `p` (int, 可选): 页码，默认 `1`，最大 `100`
  - `ps` (int, 可选): 每页条数，默认 `10`，最大 `50`
  - `s` (string, 可选): 排序字段，默认 `relation`。可选值：`relation`（相关度）、`applicationDate`（申请日）、`documentDate`（公开日）、`rank`（专利评级）。可在 `applicationDate`、`documentDate` 前加 `!` 表示降序。
  - `hl` (int, 可选): 是否高亮，`0`（默认，不高亮）或 `1`（高亮）

**成功响应**（脚本已提取核心字段，不含 `data` 包装层）：
```json
{
  "total": 58981,
  "page": 1,
  "totalPages": 5899,
  "patents": [
    {
      "id": "CN108251808A",
      "title": "铜掺杂多层石墨烯的制备方法",
      "summary": "...",
      "applicant": "昆明物理研究所",
      "applicationDate": "2018-06-05",
      "documentNumber": "CN108251808A",
      "documentDate": "2018-07-06",
      "legalStatus": "公开",
      "type": "发明公开",
      "mainIpc": "C23C14/35"
    }
  ]
}
```

### 2. 专利基本信息接口

- **URL**: `/api/patent/base`
- **方法**: GET
- **参数**:
  - `id` (string, 必填): 专利唯一ID，如 `CN101864098B`
  - `t` (string, 必填): Token
  - `v` (string, 必填): 版本号 `1`

**成功响应**：
```json
{
  "patent": {
    "id": "CN1064309C",
    "title": "光学热塑性氨基甲酸乙酯树脂透镜制造方法及其透镜",
    "summary": "...",
    "ipc": "B29D11/00; B29C47/00; G02B1/04; G02B3/00",
    "applicant": "株式会社朝日光学; 奥普梯玛公司",
    "applicationDate": "1998-04-17",
    "documentNumber": "CN1064309C",
    "documentDate": "2001-04-11",
    "legalStatus": "失效专利"
  }
}
```

### 3. 专利权利要求

- **URL**: `/api/patent/claims`
- **方法**: GET
- **参数**:
  - `id` (string, 必填): 专利唯一ID
  - `t` (string, 必填): Token
  - `v` (string, 必填): 版本号 `1`
- **说明**: 返回专利权利要求书全文，文本在 `patent.claims` 中。

**成功响应**：
```json
{
  "patent": {
    "id": "CN103532200B",
    "applicationNumber": "CN201310512089.5",
    "documentNumber": "CN103532200B",
    "claims": "1.一种新能源汽车的电池管理系统..."
  }
}
```

### 4. 专利说明书全文

- **URL**: `/api/patent/desc`
- **方法**: GET
- **参数**:
  - `id` (string, 必填): 专利唯一ID
  - `t` (string, 必填): Token
  - `v` (string, 必填): 版本号 `1`
- **说明**: 返回专利说明书全文，文本在 `patent.description` 中。

**成功响应**：
```json
{
  "patent": {
    "id": "CN108251808A",
    "applicationNumber": "CN201810025878.9",
    "documentNumber": "CN108251808A",
    "description": "铜掺杂多层石墨烯的制备方法\\n技术领域\\n[0001] ..."
  }
}
```

### 5. 专利法律信息

- **URL**: `/api/patent/tx`
- **方法**: GET
- **参数**:
  - `id` (string, 必填): 专利唯一ID
  - `t` (string, 必填): Token
  - `v` (string, 必填): 版本号 `1`

**成功响应**：
```json
{
  "transactions": [
    {
      "content": "IPC(主分类): C01B 32/184\\n专利申请号: 201010263656.4\\n申请日: 2010.08.25",
      "date": "2011-03-09",
      "type": "实质审查的生效",
      "applicationNumber": "CN201010263656.4"
    },
    {
      "content": null,
      "date": "2011-01-12",
      "type": "公开",
      "applicationNumber": "CN201010263656.4"
    }
  ]
}
```

### 6. 专利引用数据

- **URL**: `/api/patent/citing`
- **方法**: GET
- **参数**:
  - `id` (string, 必填): 专利唯一ID
  - `t` (string, 必填): Token
  - `v` (string, 必填): 版本号 `1`
- **说明**: 返回三类引用数据
  - `citedList`: 被引用专利列表
  - `patentXref`: 专利引用列表
  - `noPatentXref`: 非专利引用列表

**成功响应**：
```json
{
  "citedList": [ { "id": "CN102824883A", "title": "..." } ],
  "noPatentXref": [ "杨常玲等.石墨烯的制备及其电化学性能.《电源技术》.2010..." ],
  "patentXref": [ { "id": "CN101613098A", "title": "..." } ]
}
```

### 7. 相似专利接口

- **URL**: `/api/patent/like`
- **方法**: GET
- **参数**:
  - `id` (string, 必填): 专利唯一ID
  - `t` (string, 必填): Token
  - `v` (string, 必填): 版本号 `1`

**成功响应**：
```json
{
  "patentLikeList": [
    {
      "id": "CN101941693B",
      "rank": "247.5315",
      "title": "一种石墨烯气凝胶及其制备方法",
      "applicant": "北京理工大学",
      "documentNumber": "CN101941693B",
      "documentDate": "2012-07-25"
    }
  ]
}
```

## 错误代码对照表

脚本已将错误码映射为中文说明。若请求失败，输出格式为：
```json
{
  "error": "HTTP error: 215 ...",
  "description": "异常访问，被终止，请查看接口规范...",
  "code": 215
}
```

| 代码 | 说明 |
|------|------|
| 200 | 响应成功 |
| 201 | token为空 |
| 202 | 非法token |
| 203 | 响应异常 |
| 204 | ip被拒绝访问 |
| 205 | 参数值为空 |
| 206 | 没有找到对应数据 |
| 207 | 该接口当天访问次数已经用尽 |
| 208 | 没有访问权限 |
| 209 | 版本号为空 |
| 210 | 参数错误 |
| 211 | 该等级接口当年专利总数量已经用尽 |
| 212 | 分析维度为空 |
| 213 | 分析维度不存在 |
| 214 | TOKEN类型错误 |
| 215 | 异常访问，被终止，请查看接口规范（通常因为专利ID无效或已过期，请重新通过搜索接口获取） |
| 216 | 获取年费数据异常 |
| 217 | 访问说明书附图数量超过专利总量的3倍限制 |
| 218 | 搜索、引用、相似接口总调用量超过了每日调用量的100倍限制 |
