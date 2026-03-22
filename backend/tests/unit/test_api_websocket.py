import pytest
from fastapi import WebSocket
from app.api.websocket import ConnectionManager

@pytest.mark.asyncio
async def test_connection_manager(mocker):
    manager = ConnectionManager()
    ws = mocker.Mock(spec=WebSocket)
    ws.accept = mocker.AsyncMock()
    ws.send_json = mocker.AsyncMock()
    ws.close = mocker.AsyncMock()
    
    await manager.connect(ws, "camp1")
    assert "camp1" in manager.active_connections
    assert ws in manager.active_connections["camp1"]
    
    await manager.send_personal_message({"msg": "hello"}, ws)
    ws.send_json.assert_called_with({"msg": "hello"})
    
    await manager.broadcast_to_campaign("camp1", {"msg": "world"})
    ws.send_json.assert_called_with({"msg": "world"})
    
    manager.disconnect(ws, "camp1")
    assert ws not in manager.active_connections["camp1"]
