
# 把 Gmail 新邮件推送到钉钉群机器人
# 用法
``` Bash
nohup python3 -u g.py 300 >/dev/null 2>error.log &
```

# 前言
做这个功能费了我老大劲了，首先想到的还是利用现成的软件，尝试了一圈发现都不满意。然后不想重复造轮子，就搜索如何把 Gmail 推送到钉钉，结果只搜到了诸如 Python 如何调用 Gmail API、钉钉群机器人使用这样的相关文章，竟然没找到完整造这个轮子的文章。最后就自力更生了。目前的使用体验还行，有个小问题是有时可能要登一下远程服务器手动重启程序。

本文实现方法**需要一个能同时调用 Gmail API、钉钉群机器人 API 的服务器**。  
实现效果：  
![](https://pic4.zhimg.com/v2-692572339b56cfb68082ce04349d2fdb_r.jpg)
![](https://pic4.zhimg.com/80/v2-efcc03b9f76a547b94f4fd5cfd43a8bf_1440w.jpg)

**先说下已经尝试的现成的软件。（测试时间 2020-06）**  
首先当然要试试钉钉能不能登录 Gmail，Mac、Android 端都无法登录（当然代理是开着的），我登的邮箱是 Gmail 的企业邮箱。Android 端开代理可以登录，但属于未验证的应用，Google 拒绝登录。  
![](https://pic4.zhimg.com/80/v2-e22c40dfbfd7eea92a0d6dd0202cc66f_1440w.jpg)  
用 Gmail 生成的应用专用密码登录，会收到邮件：  
![](https://pic4.zhimg.com/80/v2-12dd7915a6598b7af9ebe6ad1fb8155f_1440w.jpg])

然后，没找到 Gmail 的官方 macOS 客户端。  
最后是各类 Android 端第三方邮件 APP，主要要求是不用代理也能收信。  
网易邮箱大师：登录、收信均不需要代理，但登不上我司企业 Gmail 邮箱  
Outlook：登录需要代理、收信不需要，Android 端邮件推送一直抽风  
MIUI 自带电子邮件：登录需要代理、收信不需要，连接不稳定，有时看不了邮件  
QQ 邮箱：没亲自用，据说推送也有问题  
其他邮箱 APP 不想试了，而且有信息泄露风险。

***
下面是本文的主要内容，如何把 Gmail 邮件推送到钉钉。

# 开启 Gmail API

主要参考 这篇文章 即可，Google 现在支持中文界面。  
印象中需要注意的部分是选择创建个人或组织的应用，我的是 Gmail 企业邮箱，所以创建的应用是属于组织的，个人的应用我不确定能不能以及如何创建。  
本来我是打算这部分也全部自己截图做一遍的，但写文章时距离我完成程序已经过了 2 个月，就不想写这部分了。

一开始我尝试用 [Cloud Pub/Sub API](https://cloud.google.com/pubsub/overview?hl=zh-cn) 推送通知到钉钉 Webhook，结果出错：  
```
googleapiclient.errors.HttpError: <HttpError 403 when requesting https://www.googleapis.com/gmail/v1/users/me/watch?alt=json returned "Error sending test message to Cloud PubSub projects/gmail-push-XXXXX/topics/my-topic : User not authorized to perform this action.">
```

而且该方式推送的消息格式不能自定义，与钉钉机器人消息格式不匹配

# 代码讲解
下面讲解代码。注释我已经写得比较详细了。主要功能就是调用 Gmail API 读邮件，调用钉钉 API 发邮件。代码里的函数比较多，我只用了一部分，其他调用 Gmai API 函数的功能无法保证可用。

具体我与前人不同，自己实现的函数是 check_new_email，功能是通过 historyId 检查新邮件。
## startHistoryId 与 HistoryId
无符号整数，按时间顺序增长，增量随机。通常有效期至少一周，少数情况下只有几小时。如果 startHistoryId 无效或过期会返回 404。  
**可以确定的是**：读取邮件（网页上读取）会导致 HistoryId 增加。**感觉**：每次调用 service.users().history().list() 响应的 HistoryId 都会增长（即使收件箱无变化）  
![](https://pic2.zhimg.com/80/v2-cdf4071c5494629219526c07c5185b39_1440w.jpg)

get_messages_by_query 函数具有搜索功能，搜索时用的 subject 好像不支持中文，用了邮件的编码也搜不到。  
在 Gmail 网页上能看到的 Message-ID 不是 Gmail API 的邮件 id。

代码部分就这么多（隔时间太久，想不起来细节了。）

# 钉钉群机器人配置

## 开启钉钉群机器人
创建单人群聊：手机，面对面建群，不添加其他人  
添加机器人：智能群助手 - 添加机器人 - 自定义机器人
![](https://pic2.zhimg.com/80/v2-97409d7ac43d11e72f8107d78724da69_1440w.jpg)

头像、名字可以自定义。「安全设置」如图
![](https://pic3.zhimg.com/80/v2-9902a7a1c0b56fdbe530cf8bd93e5042_1440w.jpg)

记录 WebHook 地址里面的 access_token，这个要写在文件里。

测试钉钉机器人：
```
curl 'https://oapi.dingtalk.com/robot/send?access_token=token' \
-H 'Content-Type: application/json' \
-d '{"msgtype": "text","text": {"content": "关键词"}}'
```

我的 VPS 在美国，调用一次 API 花 7 秒时间，在服务器上解析域名，查到的 IP 地址是阿里在美国的服务器，不需要考虑跨墙问题。

[钉钉群机器人开发文档](https://open.dingtalk.com/document/group/custom-robot-access)

钉钉每个机器人**每分钟最多发送 20 条**，如果超过 20 条，会限流 10 分钟。

# 正式使用

**第一次运行前需要准备下列文件**：创建并填写 access_token 文件，创建 history_id 文件，准备好 credentials.json。

## Gmail API 访问授权

第一次运行程序后，会弹出一个页面，此时需要把权限授予应用。  
[查看 Google 帐号第三方访问权限](https://myaccount.google.com/security-checkup)  
![](https://pic3.zhimg.com/80/v2-9967829af2bb983cafe39e6ccc86078e_1440w.jpg)

使用 virtualenv（可选）：source venv/bin/activate

安装程序运行所需模块：pip3 install 。各人环境不同，具体模块请看代码

设为 5 分钟推送一次。解释一下参数，文件名的面的 300，是指 300 秒，其他的一般无需修改。
```
nohup python3 -u g.py 300 >/dev/null 2>error.log &
```
查看是否运行成功：
```
ps aux | grep "g.py"
```
成功的回显应该有 2 行

# 目前存在的问题：

每隔不定期的时间，会产生：BrokenPipeError: [Errno 32] Broken pipe 错误，错误原因我不明白。可能只是 VPS 网络波动。如果有读者**亲自**解决过这个问题，还请赐教。

# 参考文章

Gmail API 调用：[Python 读取gmail, Python 搜索gmail, Python操作gmail, How to access Gmail using Python](https://justcode.ikeepstudying.com/2019/09/python-%E8%AF%BB%E5%8F%96gmail-python-%E6%90%9C%E7%B4%A2gmail-python%E6%93%8D%E4%BD%9Cgmail-how-to-access-gmail-using-python/)

官方文档：[Gmail API Reference](https://developers.google.com/gmail/api/v1/reference)

[钉钉群机器人开发文档](https://open.dingtalk.com/document/group/custom-robot-access)

[Python 解析邮件](https://www.liaoxuefeng.com/wiki/1016959663602400/1017800447489504)
