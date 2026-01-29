###############################################################################
#                                第一阶段：开始
###############################################################################
# 使用最小化的 Alpine 基础镜像，维护者信息
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/mcr.microsoft.com/playwright/python:v1.56.0 AS build
LABEL maintainer="ckf10000@sina.com"

###############################################################################
#                                环境变量与路径
###############################################################################

# 设置工作目录路径
WORKDIR /app


###############################################################################
#                               文件添加与权限设置
###############################################################################
# 复制整个应用代码到容器中
COPY ./ /app/

# 安装依赖
RUN pip install --use-pep517 --timeout 30 --root-user-action=ignore --user --no-cache-dir --no-warn-script-location -r /app/requirements.txt -i https://mirrors.huaweicloud.com/repository/pypi/simple



###############################################################################
#                                第二阶段：开始
###############################################################################

FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/mcr.microsoft.com/playwright/python:v1.56.0

# 设置环境变量
ENV LOCAL_PKG="/root/.local"
ENV WORKDIR=/app

# 将从构建阶段复制的依赖文件添加到容器中
COPY --from=build ${LOCAL_PKG} ${LOCAL_PKG}
COPY --from=build $WORKDIR $WORKDIR

# 安装运行所需的系统库
RUN apt-get update && apt-get install -y curl wget
RUN ln -sf ${LOCAL_PKG}/bin/* /usr/local/bin/


WORKDIR $WORKDIR


EXPOSE 9996
###############################################################################
#                                   启动服务
###############################################################################
ENTRYPOINT ["python"]
CMD ["app.py"]

###############################################################################
#                                健康检查
###############################################################################

# 健康检查，每隔30秒检查一次，超时5秒，连续失败3次则标记为不健康
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --spider -q http://127.0.0.1:9996/healthCheck || exit 1