"""MCP stdio 서버가 제공하는 tool 목록을 덤프하는 수동 스크립트 — 운영 환경 진단용."""

import asyncio

from mcp.client.session import ClientSession  # pyright: ignore[reportMissingImports]
from mcp.client.stdio import (  # pyright: ignore[reportMissingImports]
    StdioServerParameters,
    stdio_client,
)


async def main():
    # 여기에 아까 맥북 로컬에서 빌드했던 Node.js index.js 절대 경로를 넣으세요!
    local_node_path = "/Users/homesul/-rpgmaker-mz-mcp/dist/index.js"

    server_params = StdioServerParameters(command="node", args=[local_node_path])

    print("MCP 서버에 연결 중...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("✅ 연결 성공! 사용 가능한 툴 목록을 가져옵니다:\n")
            tools_response = await session.list_tools()

            for tool in tools_response.tools:
                print(f"🔹 툴 이름: '{tool.name}'")
                print(f"   설명: {tool.description}")
                print(f"   필요한 인자(스키마): {tool.inputSchema}\n")


asyncio.run(main())
