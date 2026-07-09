"""
G9 智能销售运营决策系统 — 全局配置
"""
import os
import warnings
warnings.filterwarnings('ignore')

# 路径配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')
MODELS_DIR = os.path.join(BASE_DIR, 'models')
EXCEL_PATH = os.path.join(BASE_DIR, 'G9_销售运营数据.xlsx')

# 随机种子
SEED = 42

# 中文字体配置
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
import matplotlib.pyplot as plt
plt.rcParams['figure.dpi'] = 150
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['savefig.bbox'] = 'tight'

# 统一配色方案 — dataviz 标准
PALETTE = {
    'primary': '#2563EB',
    'secondary': '#F97316',
    'success': '#10B981',
    'danger': '#EF4444',
    'warning': '#F59E0B',
    'info': '#06B6D4',
    'neutral': '#6B7280',
    'dark': '#1E293B',
    'light': '#F8FAFC',
}

# 分类配色
CITY_COLORS = {
    '北京': '#DC143C', '上海': '#4169E1', '广州': '#FF8C00', '深圳': '#2E8B57',
    '杭州': '#9370DB', '成都': '#CD853F', '南京': '#4682B4', '重庆': '#B22222',
    '武汉': '#DAA520', '西安': '#708090'
}

CHANNEL_COLORS = {
    '官网': '#2563EB', '懂车帝': '#F97316', '抖音': '#EF4444',
    '车展': '#10B981', '朋友推荐': '#8B5CF6', '门店': '#F59E0B'
}

METHOD_COLORS = {'电话': '#2563EB', '微信': '#10B981', '面谈': '#F97316'}

RANK_COLORS = {'初级': '#10B981', '中级': '#2563EB', '高级': '#F97316', '资深': '#8B5CF6'}

PERF_COLORS = {'A': '#10B981', 'B': '#2563EB', 'C': '#F59E0B', 'D': '#EF4444'}

CATEGORICAL_10 = ['#2563EB', '#F97316', '#10B981', '#EF4444', '#8B5CF6',
                  '#EC4899', '#06B6D4', '#F59E0B', '#84CC16', '#6B7280']

# 画图辅助函数
def save_fig(fig, name, week='W1'):
    """统一保存图表"""
    path = os.path.join(REPORTS_DIR, f'{week}_charts', name)
    fig.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'  ✓ 已保存: {path}')

def create_figure(figsize=(12, 6), title='', subtitle=''):
    """创建统一样式的图表"""
    fig, ax = plt.subplots(figsize=figsize)
    if title:
        fig.suptitle(title, fontsize=16, fontweight='bold', y=1.02)
    if subtitle:
        ax.set_title(subtitle, fontsize=11, color='#6B7280', pad=10)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    return fig, ax

def add_value_labels(ax, fmt='{:.1f}', rotation=0, fontsize=8):
    """在柱状图上添加数值标签"""
    for bar in ax.patches:
        height = bar.get_height()
        if height > 0:
            ax.text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                    fmt.format(height), ha='center', va='bottom',
                    fontsize=fontsize, rotation=rotation)

print('✅ 配置模块加载完成')
