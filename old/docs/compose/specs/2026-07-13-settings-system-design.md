> [!NOTE]
> This document may not reflect the current implementation.
> See the final report for up-to-date state:
> [Final Report](../reports/settings-system.md)

# [S1] Problem
当前设置对话框中的语言和外观选择框只是UI组件，没有连接任何信号槽来实际应用更改。用户无法切换语言或主题。

# [S2] Solution overview
创建设置管理系统，支持语言和主题的立即切换。设置保存在用户目录的.codexU/config.json中。

# [S3] Architecture
## Components
1. **SettingsManager** - 设置管理器，负责加载、保存和应用设置
2. **SettingsDialog** - 设置对话框，连接UI组件到设置管理器
3. **ThemeManager** - 主题管理器，负责应用主题样式
4. **TranslationManager** - 翻译管理器，负责应用语言设置

## Data Flow
1. 用户在SettingsDialog中选择语言或主题
2. SettingsDialog调用SettingsManager保存设置
3. SettingsManager通知ThemeManager或TranslationManager
4. ThemeManager更新所有UI组件的样式表
5. TranslationManager更新所有UI组件的文本

## File Structure
- `app/utils/settings.py` - SettingsManager类
- `app/utils/theme.py` - ThemeManager类  
- `app/utils/translation.py` - TranslationManager类
- `app/settings_dialog.py` - 修改，连接信号槽
- `app/main_window.py` - 修改，启动时加载设置
- `app/ui/dashboard.py` - 修改，支持动态文本更新

# [S4] Settings Manager
## Responsibilities
- 加载设置从`~/.codexU/config.json`
- 保存设置到`~/.codexU/config.json`
- 提供默认值
- 发送设置变更信号

## API
```python
class SettingsManager:
    def __init__(self)
    def get_language(self) -> str  # "zh" or "en"
    def get_theme(self) -> str  # "auto", "light", "dark"
    def set_language(self, lang: str)
    def set_theme(self, theme: str)
    def load(self)
    def save(self)
```

# [S5] Theme Manager
## Responsibilities
- 根据主题设置更新所有UI组件的样式表
- 支持自动（跟随系统）、浅色、深色三种主题
- 提供主题切换的立即反馈

## Implementation
- 使用Qt的setStyleSheet动态更新样式
- 为每个主题预定义颜色方案
- 自动检测系统主题（Windows）

# [S6] Translation Manager  
## Responsibilities
- 根据语言设置更新所有UI组件的文本
- 支持中文和英文
- 提供翻译字典

## Implementation
- 使用字典存储翻译文本
- 提供`tr(key)`函数获取翻译
- 在UI组件中使用翻译键

# [S7] Settings Dialog Changes
## Responsibilities
- 连接语言选择框到SettingsManager
- 连接外观选择框到SettingsManager
- 提供实时预览

## Implementation
- 在`_general_tab()`中连接语言选择框的`currentIndexChanged`信号
- 在`_display_tab()`中连接外观选择框的`currentIndexChanged`信号
- 调用SettingsManager保存设置

# [S8] Application Startup
## Responsibilities
- 在启动时加载设置
- 应用初始主题和语言
- 初始化设置管理器

## Implementation
- 在`main.py`中创建SettingsManager实例
- 调用`load()`加载设置
- 初始化ThemeManager和TranslationManager
- 应用初始设置

# [S9] Error Handling
## File Operations
- 如果配置文件不存在，使用默认值
- 如果配置文件损坏，使用默认值并重新创建
- 如果目录不存在，创建目录

## Theme Application
- 如果主题应用失败，回退到深色主题
- 记录错误日志

# [S10] Testing
## Unit Tests
- 测试SettingsManager的加载和保存
- 测试默认值
- 测试错误处理

## Integration Tests
- 测试语言切换立即生效
- 测试主题切换立即生效
- 测试设置持久化