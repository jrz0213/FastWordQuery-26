<img width="197" height="446" alt="image" src="https://github.com/user-attachments/assets/6678c91d-9a24-4c75-8331-24707b3aaa31" />#  更新内容 

- **日志系统**：新增完整的日志记录功能，方便追踪查询异常与排查 Bug。（日志文件位于插件根目录）
    <img width="857" height="287" alt="image" src="https://github.com/user-attachments/assets/81124210-e697-42f1-9a28-4314ba480160" />
    <img width="157" height="338" alt="image" src="https://github.com/user-attachments/assets/f239c1f8-e3e4-4e4e-94be-a208dfab3d00" />


- **自动化检测**：
  - 新增数据库状态创建检测机制。
  - 支持本地词典脚本自动检测（当 `.py` 脚本与 `.mdx` 文件同名且处于同一目录时自动识别）。
    检测到同名脚本时，会识别对应路径和文件名，右侧会出现'√'，并自动填入词典地址
  <img width="266" height="326" alt="image" src="https://github.com/user-attachments/assets/6e016b23-c0d2-4fb3-b3ac-db37ad87ccad" />
  <img width="197" height="446" alt="image" src="https://github.com/user-attachments/assets/600c58ce-28e9-4f09-81ac-49c65ba4b103" />
- **多媒体支持**：增强对多个 `.mdd` 文件的支持，完善本地词典的音频/图片加载，解决牛津9和牛津10词典无法导入单词和例句发音问题。（上图橙色）
 
- **UI 与交互优化**：
  - 优化本地文件夹面板的显示，可清晰查看所有被检测到的 `.mdx` 文件。
  - 修复了当存在多个本地词典脚本时，仅第一个词典能够显示默认选项的 Bug。
- **现代库适配**：移除过时的 PyQt5 代码，全面适配现代 Anki 环境。
- **打开程序由系统接管**
# -------------------


# FastWordQuery Addon For Anki

  [Supported Dictionaries](docs/services.md)

  [为单词添加真人发音（朗文mdx词典）](docs/get_mdx_ldoce6_sounds.md)



## Features

This addon query words definitions or examples etc. fields from local or online dictionaries to fill into the Anki note.  
It forks from [WordQuery](https://github.com/finalion/WordQuery), added **multi-thread** feature, improve stability, and some other features.

  - Querying Words and Making Cards, IMMEDIATELY!
  - Support querying in mdx and stardict dictionaries.
  - Support querying in web dictionaries.
  - Support **Multi-Thread** to query faster.

## Install

   1. Just copy the src folder to the plugin folder, or rename it to fastwq, whatever.



## Setting

### Shortcut
  1. Click Menu **"Tools -> Add-ons -> FastWQ -> Edit..."**  
      ![](screenshots/setting_menu.png)
  2. Edit the code and click **Save**  
      ![](screenshots/setting_shortcut.png)

### Config
  1. In Browser window click menu **"FastWQ -> Options"**  
      ![](screenshots/setting_config_01.png)

  2. Click **Settings** button in the Options window  
      ![](screenshots/setting_config_02.png)  
      - **Force Updates of all fields** : Update all fields even if it's None
      - **Ignore Accents** : Ignore accents symbol of word in querying
      - **Auto check new version** : Check new version at startup
      - **Number of Threads** : The number of threads running at the same time
  
  
## Usage

### Set the query fields

  1. Click menu **"Tools ->  FastWQ"**, or in Browser window click menu **"FastWQ -> Options"**
  2. Select note type  
      ![](screenshots/options_01.png)
  3. Select Dictionary  
      ![](screenshots/options_02.png)
  4. Select Fields  
      ![](screenshots/options_03.png)
  5. Click **OK** button  

### 'Browser' Window
  1. Select single or multiple words, click menu **"FastWQ -> Query Selected"** or press shortcut Default is **Ctrl+Q**.  
      ![](screenshots/options_04.png)
  2. Waiting query finished  
      ![](screenshots/use_01.png)
  
### 'Add' Window
  1. Click Add button in Browser window, open Add window  
      ![](screenshots/use_02.png)
  2. Edit key field and click Query button  
      ![](screenshots/use_03.png)


## Other Projects Used
  - [mdict-query](https://github.com/mmjang/mdict-query)
  - [pystardict](https://github.com/lig/pystardict)
  - [WordQuery](https://github.com/finalion/WordQuery)
  - [AnkiHub](https://github.com/dayjaby/AnkiHub)
  - [snowball_py](https://github.com/shibukawa/snowball_py)
