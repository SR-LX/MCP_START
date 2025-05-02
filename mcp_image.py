# 导入必要的库和模块
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from pydantic import Field
import uvicorn
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from starlette.responses import JSONResponse
from volcengine.visual.VisualService import VisualService
import json
import logging
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API配置 - 从环境变量获取
VOLC_ACCESS_KEY = os.environ.get("VOLC_ACCESS_KEY", "")
VOLC_SECRET_KEY = os.environ.get("VOLC_SECRET_KEY", "")

# 创建FastMCP实例，用于处理会话
mcp=FastMCP(name='Demo')
# 创建SseServerTransport实例，用于处理IO（SSE和POST）
sse_transport=SseServerTransport('/messages/')

# 创建火山引擎视觉服务实例
visual_service = VisualService()
# 配置火山引擎访问凭证
visual_service.set_ak(VOLC_ACCESS_KEY)
visual_service.set_sk(VOLC_SECRET_KEY)

@mcp.resource("greeting://{name}")
def get_greeting(name: str) -> str:
    """Get a personalized greeting"""
    return f"Hello, {name}!"


@mcp.tool(name="generate_image",description='生成图片')
async def generate_image(
    prompt: str = Field(description='输入提示词到mcp服务器'),
    file_name: str = Field(description='输入文件名到mcp服务器'),
    width: int = 512, 
    height: int = 512,
    use_sr: bool = True,
    use_pre_llm: bool = False,
    scale: float = 3.5,
    ddim_steps: int = 25,
    seed: int = -1,
    req_schedule_conf: str = "general_v20_9B_pe"
):
    try:
        # 构建请求体
        form = {
            "req_key": "high_aes_general_v21_L",
            "prompt": prompt,
            "model_version": "general_v2.1_L",
            "req_schedule_conf": req_schedule_conf,
            "seed": seed,
            "scale": scale,
            "ddim_steps": ddim_steps,
            "width": width,
            "height": height,
            "use_pre_llm": use_pre_llm,
            "use_sr": use_sr,
            "return_url": True,
            "logo_info": {
                "add_logo": False
            }
        }

        # 调用火山引擎API
        response = visual_service.cv_process(form)
        
        if not response or "data" not in response:
            return f"API调用失败: 未获取到有效响应"
        
        # 获取API返回的所有相关数据
        data = response["data"]
        image_urls = data.get("image_urls", [])
        binary_data_base64 = data.get("binary_data_base64", [])
        pe_result = data.get("pe_result", "")
        predict_tags_result = data.get("predict_tags_result", "")
        rephraser_result = data.get("rephraser_result", "")
        request_id = data.get("request_id", "")
        algorithm_base_resp = data.get("algorithm_base_resp", {})
        
        # 获取响应的其他元数据
        code = response.get("code", 0)
        message = response.get("message", "")
        status = response.get("status", 0)
        time_elapsed = response.get("time_elapsed", "")
        
        if image_urls:
            return {
                "success": True,
                "message": "图片生成完成",
                "urls": image_urls,
                "binary_data_base64": binary_data_base64,
                "pe_result": pe_result,
                "predict_tags_result": predict_tags_result,
                "rephraser_result": rephraser_result,
                "request_id": request_id,
                "algorithm_base_resp": algorithm_base_resp,
                "code": code,
                "api_message": message,
                "status": status,
                "time_elapsed": time_elapsed
            }
        else:
            return {
                "success": False,
                "error": "没有生成图片URL"
            }
                
    except Exception as e:
        return {
            "success": False,
            "error": f"生成图片出错: {str(e)}"
        }

# 定义一个工具函数，用于获取网站内容@mcpserver.tool(name='fetch',description='Fetches a website and returns its content')
@mcp.tool(name='抓取', description='用来抓取网站内容')
async def fetch_website(url: str = Field(description="网站地址，例如：example.com")):
    print('fetching....')  # 打印调试信息
    # 检查URL是否以http://或https://开头，如果没有则添加https://
    if not url.startswith('http://') and not url.startswith('https://'):
        url='https://'+url
    # 使用httpx库异步获取网站内容
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response=await client.get(url)
        # 如果响应状态码不是200，返回错误信息
        if response.status_code!=200: 
            return f'Error fetching {url}: {response.status_code}'
        # 返回网站内容
        return response.text

# 定义一个异步函数，用于处理SSE连接
async def sse_handler(request):
    async with sse_transport.connect_sse(request.scope,request.receive,request._send) as streams:
        # 运行MCP服务器，保持SSE会话
        await mcp._mcp_server.run(streams[0],streams[1],mcp._mcp_server.create_initialization_options())

# 定义根路由处理函数 - 必须先定义，后使用
async def root(request):
    return JSONResponse({"message": "服务已启动"})

# 使用Starlette框架配置应用
app=Starlette(
    debug=True,  # 启用调试模式
    routes=[
        Route("/", endpoint=root),  # 添加根路由
        Route('/sse',endpoint=sse_handler),  # 配置SSE路由
        Mount('/messages/',app=sse_transport.handle_post_message)  # 配置消息路由
    ]
)

# 使用Uvicorn运行应用
if __name__ == '__main__':
 uvicorn.run(app,host='0.0.0.0',port=8001)


