/**
 * 应急数据清洗与可视化系统 - 前端交互逻辑
 * 包含：文件上传、数据清洗、ECharts渲染、日志展示、文件下载
 */

// ==================== 全局状态 ====================
let currentResult = null;
let selectedFile = null;

// ==================== 文件选择 ====================
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

// ==================== 拖拽上传 ====================
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

// ==================== 提示消息 ====================
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
    document.getElementById('btnDownloadClean').onclick = () => downloadFile('output');
    document.getElementById('btnDownloadLog').onclick = () => downloadFile('log');
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

// ==================== 文件下载 ====================
function downloadFile(type) {
    if (!currentResult) return;
    const filename = type === 'output'
        ? currentResult.output_filename
        : currentResult.log_filename;
    window.open('/api/download/' + encodeURIComponent(filename), '_blank');
}
