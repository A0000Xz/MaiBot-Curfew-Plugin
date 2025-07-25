# MaiBot-Curfew-Plugin

这里是麦麦BOT的宵禁插件！

目前0.9.1分支支持main版0.9.1，main分支会持续跟进最新dev进行更新。

使用本插件前请至少要在配置文件设置管理用户，这样能够方便其他功能，另外你的麦麦必须是某个群的管理员，这也不必多说了吧？

本插件不会在启动时就启动宵禁机制，需要你配置好以后自行打开，打开后只要你的麦麦不崩溃，不被关掉，它就会24小时工作，在规定时段自动打开或者关闭群体禁言。切换开关状态请使用指令，会在下面介绍。

你可以在配置文件配置该插件一些功能细节，例如这样：

![QQ_1750503337271](https://github.com/user-attachments/assets/4c2b257f-401f-4608-80b2-3a3691ef00dd)

值得一提的是，为了方便一些特殊情况，宵禁插件搭载了一些指令系统（可能有点臃肿），但它旨在帮助你在“无法碰到电脑，无法直接修改配置文件，但现在迫切需要改变其行为逻辑时”的情况下修改配置。

就像这样：

![QQ_1750503560893](https://github.com/user-attachments/assets/58a3e82c-9e70-43f2-971f-6447e7d48c88)

如图所示，这套指令甚至可以在私聊环境下使用（不过会有特殊参数被禁用），除了管理用户的私聊环境以外，也只有插件被允许生效的群聊才会回应指令。

此外，它还有一些基本的纠错能力，可以防止你填一些奇奇怪怪的参数进去，例如：

![QQ_1750503866580](https://github.com/user-attachments/assets/62cc5c7d-b202-4821-a682-4d4086e8a7fb)

![QQ_1750503909455](https://github.com/user-attachments/assets/aa2ddd68-1c08-4750-bab9-8efaf1ea8dd0)

![QQ_1750503979167](https://github.com/user-attachments/assets/1b031182-b884-4bec-b047-c0358bdc969d)

总之，目前可用的便捷指令有：

/curfew true    #开启宵禁机制

/curfew false   #关闭宵禁机制，同时即刻解除全体禁言

/curfew time list   #列出当前设置的宵禁时间段

/curfew start_time set 23:00   #将宵禁开始时间设置为23:00（注：不能填24:00，因为定义其实是0:00，不过这么填说不定会有小彩蛋呢）

/curfew end_time set 6:00   #将宵禁开始时间设置为6:00（注：标准的填写应当是06:00，但是你这么填也不会引发错误。）

/curfew permission_group list   #列出所有插件会生效的群聊名单

/curfew permission_group add 123456789   #将群号为123456789的群加入到插件会生效的群聊配置里

/curfew permission_group remove 123456789   #将群号为123456789的群聊从插件会生效的群聊配置中移除

目前就这些内容了
