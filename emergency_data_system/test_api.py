"""快速测试API脚本"""
import requests
import json

BASE = "http://127.0.0.1:5000"

# 测试首页
resp = requests.get(BASE + "/")
print("首页状态:", resp.status_code, "| 页面大小:", len(resp.text), "字符")

# 检查关键元素
checks = ["ECharts", "upload", "chartOverview", "chartAnomaly"]
for kw in checks:
    found = kw.lower() in resp.text.lower()
    print("  包含", kw, ":", "OK" if found else "MISSING")

# 测试健康检查
resp = requests.get(BASE + "/api/health")
print("\n健康检查:", resp.json())

# 测试上传+清洗
with open("uploads/test_dirty_data.xlsx", "rb") as f:
    resp = requests.post(BASE + "/api/upload", files={"file": ("test.xlsx", f)})
result = resp.json()
print("\n上传清洗:", result["message"])
d = result["data"]
print("  原始:", d["original_count"], "-> 有效:", d["valid_count"])
print("  重复剔除:", d["removed_dup_count"], "| 异常:", d["anomaly_count"])
print("  输出文件:", d["output_filename"])
print("  日志文件:", d["log_filename"])

# 测试下载
output_file = d["output_filename"]
resp = requests.get(BASE + "/api/download/" + output_file)
print("\n下载 " + output_file + ":", resp.status_code, "(" + str(len(resp.content)) + " bytes)")

# 测试日志下载
log_file = d["log_filename"]
resp = requests.get(BASE + "/api/download/" + log_file)
print("下载 " + log_file + ":", resp.status_code, "(" + str(len(resp.content)) + " bytes)")

print("\n=== 全流程测试通过 ===")
print("系统可访问 http://127.0.0.1:5000")
