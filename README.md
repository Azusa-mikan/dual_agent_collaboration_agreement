# sub-agent-review

一个 Skill：让主 Agent 当审查者、派发的 Sub Agent 当实现者，把「实现」和「验收」拆开。

> 仓库本来是通过两个 Agent 来一写一查，但后续发现：各个平台的 Sub Agent 功能同样也能做到这一点，遂重构。

# 它干什么

如果你让一个AI来审查自己的代码，它往往会认可自己的代码然后糊弄你一下就说完成了。

本 Skill 让主 Agent 只履行审查职责，派发子 Agent 去写代码，子 Agent 汇报的，主 Agent 都会审一遍，最后完成用户派发的任务。

你完全可以和平常一样让AI实现什么功能，只不过 Agent 的工作方式将更加井井有条。

这样的好处是 Agent 上下文只有审查记录，没有实现功能的记录，上下文不臃肿。

实现功能的记录全在子 Agent 里，互不干扰且一次性，主 Agent 只看得到它最后的汇报。

如果歧义在最后也没有解决，你需要介入。

# 如何安装

如果平台可以通过 zip 文件安装，你可以通过文件列表的右上角的 `< > Code` → Download ZIP 来下载项目源码。

下载下来的 `.zip` 文件就可以供平台导入。

# 通过此 Skill 完成的项目

[notify-send-restapi](https://github.com/Azusa-mikan/notify-send-restapi)

# 许可证

[MIT](LICENSE)

制作不易，切勿收费。
