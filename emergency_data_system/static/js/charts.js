/**
 * ============================================================================
 *  应急数据清洗与可视化系统 - 前端交互逻辑
 * ============================================================================
 *
 *  本文件负责系统的全部前端交互，包括以下功能模块：
 *
 *  模块1: 文件上传
 *    - 点击上传（<input type="file">）
 *    - 拖拽上传（Drag & Drop API）
 *    - 格式校验（仅 .xlsx）
 *    - 文件选择状态管理
 *
 *  模块2: 数据清洗交互
 *    - 异步上传（Fetch API + FormData）
 *    - 进度反馈（CSS 动画进度条）
 *    - 结果渲染（统计卡片 + 图表 + 日志表格）
 *    - 错误处理（网络异常 / 服务端错误）
 *
 *  模块3: ECharts 可视化
 *    - 清洗总览柱状图（原始/有效/剔除/异常 四维对比）
 *    - 异常类型饼图（各类异常占比分布）
 *    - 月度趋势折线图（基于历史数据库统计）
 *    - 图表自适应（窗口 resize 时自动重绘）
 *
 *  模块4: 历史数据看板
 *    - 全局统计摘要（累计记录数 / 异常率 / 批次数）
 *    - 月度趋势数据（从 /api/monthly 获取）
 *    - 页面初始化时自动加载
 *
 *  模块5: 文件下载
 *    - 清洗后报表下载
 *    - 异常日志下载
 *    - 增强完整报表下载
 *
 *  设计原则:
 *    - 零外部依赖：仅依赖 ECharts（CDN 加载），无 jQuery / Vue / React
 *    - 渐进增强：历史看板加载失败不影响核心的上传清洗功能
 *    - 无障碍：所有操作提供 toast 消息反馈
 * ============================================================================
 */

// ==================== 全局状态 ====================
let currentResult = null;
let selectedFile = null;

// ==================== 模块1: 文件选择与拖拽 ====================

/**
 * 处理文件选择事件（点击上传）
 * 验证文件扩展名，更新 UI 状态，启用清洗按钮
 * @param {Event} event - 文件 input 的 change 事件
 */
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!file.name.match(/\.xlsx$/i)) {
        showToast('仅支持 .xlsx 格式文件', 'error');
        return;
    }
    selectedFile = file;
    document.getElementById('fileName').textContent = '已选择: ' + file.name;
    document.getElementById('btnUpload').disabled = false;
}

// ==================== 拖拽上传（Drag & Drop API） ====================
// 监听上传区域的 dragover / dragleave / drop 三个事件
// dragover 时添加视觉反馈（边框变色），drop 时提取文件并触发同点击上传的逻辑
const uploadZone = document.getElementById('uploadZone');
uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('dragover'); });
uploadZone.addEventListener('dragleave', e => { e.preventDefault(); uploadZone.classList.remove('dragover'); });
uploadZone.addEventListener('drop', e => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (!file) return;
    if (!file.name.match(/\.xlsx$/i)) {
        showToast('仅支持 .xlsx 格式文件', 'error');
        return;
    }
    selectedFile = file;
    document.getElementById('fileName').textContent = '已选择: ' + file.name;
    document.getElementById('btnUpload').disabled = false;
});

// ==================== Toast 提示消息 ====================
// 页面顶部固定定位的提示条，4秒后自动消失
// type='success' → 绿色背景，type='error' → 红色背景
function showToast(msg, type) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = 'toast ' + type;
    setTimeout(() => { toast.className = 'toast'; }, 4000);
}

// ==================== 上传并清洗 ====================
async function uploadAndClean() {
    if (!selectedFile) return;

    const btn = document.getElementById('btnUpload');
    const progressBar = document.getElementById('progressBar');

    btn.disabled = true;
    btn.textContent = '清洗中...';
    progressBar.classList.add('active');

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const resp = await fetch('/api/upload', { method: 'POST', body: formData });
        const result = await resp.json();

        if (result.success) {
            currentResult = result.data;
            showToast('清洗完成！' + result.message, 'success');
            renderAll(result.data);
        } else {
            showToast('清洗失败: ' + result.message, 'error');
        }
    } catch (err) {
        showToast('网络错误，请检查服务是否正常运行', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '一键智能清洗';
        progressBar.classList.remove('active');
    }
}

// ==================== 渲染所有结果 ====================
function renderAll(data) {
    // 显示统计卡片
    document.getElementById('statsGrid').style.display = 'grid';
    animateNumber('statOriginal', data.original_count);
    animateNumber('statValid', data.valid_count);
    animateNumber('statDup', data.removed_dup_count);
    animateNumber('statAnomaly', data.anomaly_count);

    // 显示图表
    document.getElementById('chartsGrid').style.display = 'grid';
    renderOverviewChart(data);
    renderAnomalyPieChart(data);

    // 显示日志
    document.getElementById('logCard').style.display = 'block';
    renderLogTable(data.anomaly_logs);
    document.getElementById('logCount').textContent =
        '（共 ' + data.anomaly_logs.length + ' 条异常记录）';

    // 启用下载按钮
    document.getElementById('btnDownloadClean').disabled = false;
    document.getElementById('btnDownloadLog').disabled = false;
    document.getElementById('btnDownloadEnhanced').disabled = false;
    document.getElementById('btnDownloadClean').onclick = () => downloadFile('output');
    document.getElementById('btnDownloadLog').onclick = () => downloadFile('log');
    document.getElementById('btnDownloadEnhanced').onclick = () => downloadFile('enhanced');
}

// ==================== 数字动画 ====================
function animateNumber(id, target) {
    const el = document.getElementById(id);
    const start = parseInt(el.textContent) || 0;
    const duration = 800;
    const startTime = performance.now();

    function update(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        const current = Math.round(start + (target - start) * progress);
        el.textContent = current;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ==================== 数据清洗总览柱状图 ====================
function renderOverviewChart(data) {
    const dom = document.getElementById('chartOverview');
    if (window._overviewChart) window._overviewChart.dispose();
    const chart = echarts.init(dom);
    window._overviewChart = chart;

    chart.setOption({
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' }
        },
        grid: { left: 60, right: 30, top: 20, bottom: 30 },
        xAxis: {
            type: 'category',
            data: ['原始数据', '有效数据', '剔除重复', '异常数据'],
            axisLabel: { fontSize: 12 }
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            axisLabel: { fontSize: 12 }
        },
        series: [{
            type: 'bar',
            data: [
                { value: data.original_count, itemStyle: { color: '#2d6aa0' } },
                { value: data.valid_count, itemStyle: { color: '#27ae60' } },
                { value: data.removed_dup_count, itemStyle: { color: '#f39c12' } },
                { value: data.anomaly_count, itemStyle: { color: '#e74c3c' } }
            ],
            barWidth: '50%',
            label: {
                show: true,
                position: 'top',
                fontSize: 14,
                fontWeight: 'bold'
            }
        }]
    });

    window.addEventListener('resize', () => chart.resize());
}

// ==================== 异常类型分布饼图 ====================
function renderAnomalyPieChart(data) {
    const dom = document.getElementById('chartAnomaly');
    if (window._anomalyChart) window._anomalyChart.dispose();
    const chart = echarts.init(dom);
    window._anomalyChart = chart;

    // 统计各类异常数量
    const typeCount = {};
    (data.anomaly_logs || []).forEach(log => {
        const t = log['异常类型'] || '其他';
        typeCount[t] = (typeCount[t] || 0) + 1;
    });

    const pieData = Object.entries(typeCount).map(([name, value]) => ({ name, value }));

    if (pieData.length === 0) {
        pieData.push({ name: '无异常', value: 1 });
    }

    chart.setOption({
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c} 条 ({d}%)'
        },
        legend: {
            orient: 'vertical',
            right: 10,
            top: 'center',
            textStyle: { fontSize: 12 }
        },
        series: [{
            type: 'pie',
            radius: ['45%', '75%'],
            center: ['40%', '50%'],
            data: pieData,
            emphasis: {
                itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.5)' }
            },
            label: { fontSize: 12 },
            itemStyle: {
                borderRadius: 4,
                borderColor: '#fff',
                borderWidth: 2
            }
        }],
        color: ['#e74c3c', '#f39c12', '#e67e22', '#95a5a6', '#3498db']
    });

    window.addEventListener('resize', () => chart.resize());
}

// ==================== 异常日志表格 ====================
function renderLogTable(logs) {
    const tbody = document.getElementById('logTableBody');
    if (!logs || logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#27ae60;">本次清洗未发现异常数据</td></tr>';
        return;
    }

    const badgeType = {
        '必填字段缺失': 'badge-warn',
        '联系方式格式错误': 'badge-error',
        '企业名称缺失': 'badge-error',
    };

    tbody.innerHTML = logs.map(log => {
        const highlight = (val) => {
            if (String(val).includes('待补充')) {
                return `<span class="highlight-fill">${val}</span>`;
            }
            return val;
        };
        return `
        <tr>
            <td>第 ${log['行号']} 行</td>
            <td>${log['字段']}</td>
            <td>${highlight(log['原始值'])}</td>
            <td><span class="badge ${badgeType[log['异常类型']] || 'badge-warn'}">${log['异常类型']}</span></td>
            <td>${highlight(log['处理方式'])}</td>
        </tr>
    `}).join('');
}

// ==================== 历史数据看板 ====================

/**
 * 加载全局统计数据并渲染历史概览
 * 在页面加载完成后调用，展示所有历史批次的汇总信息
 */
async function loadHistoryDashboard() {
    try {
        const [statsResp, monthlyResp] = await Promise.all([
            fetch('/api/stats').then(r => r.json()),
            fetch('/api/monthly').then(r => r.json()),
        ]);

        if (statsResp.success && statsResp.data.total_records > 0) {
            renderStatsSummary(statsResp.data);
            if (monthlyResp.success && monthlyResp.data.length > 0) {
                renderMonthlyTrend(monthlyResp.data);
            }
        }
    } catch (err) {
        // 历史看板加载失败不影响主功能
        console.log('历史看板: 暂无数据');
    }
}

/**
 * 渲染全局统计摘要（累计处理量 + 异常率）
 * 插入页面底部的总结区域
 */
function renderStatsSummary(stats) {
    const container = document.getElementById('historySummary');
    if (!container) return;

    container.style.display = 'block';
    document.getElementById('histTotalRecords').textContent = stats.total_records || 0;
    document.getElementById('histAnomalyRate').textContent = stats.anomaly_rate || '0%';
    document.getElementById('histBatches').textContent = stats.total_batches || 0;
}

/**
 * 渲染月度趋势折线图
 * 展示各月份数据上报量的变化趋势
 */
function renderMonthlyTrend(monthlyData) {
    const dom = document.getElementById('chartMonthly');
    if (!dom) return;

    // 确保父容器可见
    const monthlySection = document.getElementById('monthlySection');
    if (monthlySection) monthlySection.style.display = 'block';

    if (window._monthlyChart) window._monthlyChart.dispose();
    const chart = echarts.init(dom);
    window._monthlyChart = chart;

    const months = monthlyData.map(d => d.month);
    const counts = monthlyData.map(d => d.count);

    chart.setOption({
        title: {
            text: '累计 ' + counts.reduce((a, b) => a + b, 0) + ' 条',
            textStyle: { fontSize: 12, color: '#888' },
            left: 'center',
            top: 5,
        },
        tooltip: {
            trigger: 'axis',
            formatter: function(params) {
                const p = params[0];
                return p.axisValue + '<br/>清洗数据量: ' + p.value + ' 条';
            }
        },
        grid: { left: 50, right: 30, top: 35, bottom: 30 },
        xAxis: {
            type: 'category',
            data: months,
            axisLabel: { fontSize: 11, rotate: 30 },
            boundaryGap: false,
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            axisLabel: { fontSize: 11 },
        },
        series: [{
            name: '数据量',
            type: 'line',
            data: counts,
            smooth: true,
            lineStyle: { color: '#2d6aa0', width: 2 },
            itemStyle: { color: '#2d6aa0' },
            areaStyle: {
                color: {
                    type: 'linear',
                    x: 0, y: 0, x2: 0, y2: 1,
                    colorStops: [
                        { offset: 0, color: 'rgba(45,106,160,0.3)' },
                        { offset: 1, color: 'rgba(45,106,160,0.05)' },
                    ],
                },
            },
            markLine: {
                silent: true,
                data: [{
                    type: 'average',
                    name: '月均',
                    lineStyle: { color: '#e74c3c', type: 'dashed' },
                }],
            },
        }],
    });

    window.addEventListener('resize', () => chart.resize());
}

// ==================== 文件下载 ====================

/**
 * 触发文件下载
 * @param {string} type - 'output' 下载清洗数据, 'log' 下载异常日志, 'enhanced' 下载完整报表
 */
function downloadFile(type) {
    if (!currentResult) return;

    let filename;
    if (type === 'output') {
        filename = currentResult.output_filename;
    } else if (type === 'enhanced') {
        filename = currentResult.enhanced_filename || currentResult.output_filename;
    } else {
        filename = currentResult.log_filename;
    }
    window.open('/api/download/' + encodeURIComponent(filename), '_blank');
}

// ==================== 页面初始化 ====================

// ==================== 用户认证 ====================

/**
 * 登录
 * 调用 /auth/login 接口，成功后刷新状态和历史看板
 */
async function doLogin() {
    const username = document.getElementById('loginUser').value.trim();
    const password = document.getElementById('loginPass').value;
    if (!username || !password) {
        showToast('请输入用户名和密码', 'error');
        return;
    }
    try {
        const resp = await fetch('/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const result = await resp.json();
        if (result.success) {
            document.getElementById('loginStatus').textContent = result.data.display_name;
            document.getElementById('loginStatus').style.color = '#27ae60';
            document.getElementById('btnClearData').style.display = 'inline-block';
            showToast(result.message, 'success');
            loadHistoryDashboard();  // 刷新数据
        } else {
            showToast(result.message, 'error');
        }
    } catch (err) {
        showToast('登录失败，请检查服务', 'error');
    }
}

/**
 * 清空当前用户的所有数据
 * 需要登录后才能操作
 */
async function clearMyData() {
    if (!confirm('确定要清空您的所有数据吗？此操作不可恢复。')) return;

    try {
        const resp = await fetch('/api/user/clear-my-data', { method: 'POST' });
        const result = await resp.json();
        if (result.success) {
            showToast(result.message, 'success');
            loadHistoryDashboard();  // 刷新看板
        } else {
            showToast(result.message, 'error');
        }
    } catch (err) {
        showToast('清空失败，请检查服务', 'error');
    }
}

/**
 * 检查登录状态（页面加载时自动调用）
 */
async function checkLoginStatus() {
    try {
        const resp = await fetch('/auth/status');
        const result = await resp.json();
        if (result.data && result.data.logged_in) {
            document.getElementById('loginStatus').textContent = result.data.display_name;
            document.getElementById('loginStatus').style.color = '#27ae60';
            document.getElementById('btnClearData').style.display = 'inline-block';
        }
    } catch (err) {
        // 未登录或网络异常，保持默认状态
    }
}

/**
 * 页面加载完毕后的初始化逻辑：
 *   1. 检查登录状态
 *   2. 加载历史数据看板
 */
document.addEventListener('DOMContentLoaded', function() {
    checkLoginStatus();
    loadHistoryDashboard();
});

