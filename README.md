# pythonGoogleDrive
### 后台简单实现谷歌硬盘api并且在浏览器通过jsonrpc远程调用

## 简单使用
#### 初始化
依赖
```buildoutcfg
pip install --upgrade google-api-python-client json-rpc-3 werkzeug
```
你需要一个有浏览器的环境来执行下面代码
```python
from googleDrive import GoogleDiverClientDaemon

if __name__ == '__main__':
    daemon = GoogleDiverClientDaemon()
    daemon.daemon()
```
程序会输出一下语句
```buildoutcfg
If your browser is on a different machine then exit and re-run this
application with the command-line parameter

  --noauth_local_webserver

[11942:11977:0831/225359.861226:ERROR:browser_gpu_channel_host_factory.cc(103)] Failed to launch GPU process.
已在现有的浏览器会话中创建新的窗口。
```
![选区_002.png](http://www.cellargalaxy.top/blog/file/2017-08-31/选区_002.png)

你的浏览器也会跳出来让你给程序授权

![选区_001.png](http://www.cellargalaxy.top/blog/file/2017-08-31/选区_001.png)

授权成功会在当前目录生成一个叫pythonGoogleDrive-client.json的文件，授权过程就是程序获取到这个文件。

程序登录你的账户需要这个文件在当前目录下。

![选区_003.png](http://www.cellargalaxy.top/blog/file/2017-08-31/选区_003.png)

之后你就可以打开[http://0.0.0.0:6600/jsonrpc](http://0.0.0.0:6600/jsonrpc)操作了
## 之后的运行
把pythonGoogleDrive-client.json文件与程序放置在相同路径下运行，短时间内不用再次授权，但不知道授权会不会失效，到时候就要再次授权了。
## 更多
详细的实现或者调用请看[googleDrive.py](https://github.com/cellargalaxy/pythonGoogleDrive/blob/master/googleDrive.py)文件。有比较详细的注释。

还有，开多线程下载不知道会不会被封号什么的，请量力食用。

博客[cellargalaxy](http://www.cellargalaxy.top/blog/article/10)