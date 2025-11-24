# cronjob-1717

#### 介绍
1717电子商务的定时任务

#### Software Architecture
Software architecture description

#### Installation

- 一、构建
  - 1.1 docker构建
    - 基于项目下的.\manifest\deploy\Dockerfile文件，在ubuntu环境下进行构建：
      - 步骤一：在linux环境下，创建构建目录，我这里以 /home/user/docker-build/tencent-message-agent 为例：mkdir -p /home/user/docker-build/tencent-message-agent
      - 步骤二：将要构建的源码文件上传至该目录，包括【 app目录，main.py文件，manifest目录，requirements.txt文件】
      - 步骤三：（可选）本项目为python项目，为什么不让构建过程中安装依赖包出现超时情况，请配置国内pip镜像源
        - 用户目录下，创建pip镜像目录：mkdir -p ~/.pip
        - 新增配置文件：vi ~/.pip/pip.conf，添加如下内容：
          - [global]
          - index-url = https://mirrors.huaweicloud.com/repository/pypi/simple
          - trusted-host = mirrors.huaweicloud.com
      - 步骤四：docker build -f /home/user/docker-build/tencent-message-agent/manifest/deploy/Dockerfile -t tencent_message_agent:1.0.0 .

- 二、部署
  - 2.1 docker-compose部署
    - 步骤一：部署前准备
      - 准备ubuntu服务器，示例中用到：
        - ubuntu@localhost:~$ sudo lsb_release -a
        - No LSB modules are available.
        - Distributor ID:	Ubuntu
        - Description:	Ubuntu 20.04.6 LTS
        - Release:	20.04
        - Codename:	focal
      - 安装docker，这里略，实例中用到：
        - ubuntu@localhost:~$ docker version
         - Client: Docker Engine - Community
          - Version:           28.1.1
          - API version:       1.49
          - Go version:        go1.23.8
          - Git commit:        4eba377
          - Built:             Fri Apr 18 09:52:18 2025
          - OS/Arch:           linux/amd64
          - Context:           default

         - Server: Docker Engine - Community
          - Engine:
          - Version:          28.1.1
          - API version:      1.49 (minimum version 1.24)
          - Go version:       go1.23.8
          - Git commit:       01f442b
          - Built:            Fri Apr 18 09:52:18 2025
          - OS/Arch:          linux/amd64
          - Experimental:     false
         - containerd:
          - Version:          1.7.27
          - GitCommit:        05044ec0a9a75232cad458027ca83437aae3f4da
         - runc:
          - Version:          1.2.5
          - GitCommit:        v1.2.5-0-g59923ef
         - docker-init:
          - Version:          0.19.0
          - GitCommit:        de40ad0
        - ubuntu@localhost:~$ docker compose version
         - Docker Compose version v2.35.1
      - ~$ mkdir -p /opt/tencent-message-agent/manifest/deploy
      - 上传项目下的 docker-compose.yaml 至 /opt/tencent-message-agent/manifest/deploy目录
      - 根据实际情况，修改docker-compose.yaml的部分配置
    - 步骤二：拉起容器 
      - ~$ docker compose -f /opt/tencent-message-agent/manifest/deploy/docker-compose.yaml up -d

#### Instructions

1.  xxxx
2.  xxxx
3.  xxxx

#### Contribution

1.  Fork the repository
2.  Create Feat_xxx branch
3.  Commit your code
4.  Create Pull Request