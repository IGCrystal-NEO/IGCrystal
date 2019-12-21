import asyncio
import json
import os
import re
from typing import Any, Union

from protobuf.index import pb            # 对应 JS 的 `import pb from "./protobuf/index.js"`
# Node.js 的 Buffer 对应 Python 的 bytes/bytearray，直接用内置
import zlib                              # 对应 zlib 的 gzip/gunzip
import logging

logger = logging.getLogger(__name__)
MAX_SAFE_INTEGER = (1 << 53) - 1        # JS Number.MAX_SAFE_INTEGER

# 异步 gzip/gunzip
async def gzip(data: bytes) -> bytes:
    return await asyncio.to_thread(zlib.compress, data)

async def gunzip(data: bytes) -> bytes:
    return await asyncio.to_thread(zlib.decompress, data)

# 随机 uint32
def random_uint() -> int:
    return int.from_bytes(os.urandom(4), 'big')

# JSON 中 bigint 处理，用于 json.dumps 的 default
def replacer(obj: Any) -> Union[int, str, Any]:
    if isinstance(obj, int):
        return str(obj) if obj >= MAX_SAFE_INTEGER else obj
    return obj

# 处理 JSON，把键从字符串变 int，并处理 hex-> 前缀
def process_json(json_obj: Any, path: list = None) -> Any:
    if path is None:
        path = []

    # 类似 Buffer.isBuffer / Uint8Array
    if isinstance(json_obj, (bytes, bytearray)):
        return json_obj

    # Array
    if isinstance(json_obj, list):
        return [process_json(item, path + [i + 1]) for i, item in enumerate(json_obj)]

    # Object
    if isinstance(json_obj, dict):
        result = {}
        for key, value in json_obj.items():
            if not re.fullmatch(r'\d+', key):
                raise ValueError(f"Key is not a valid integer: {key}")
            num_key = int(key)
            current_path = path + [key]

            # 递归
            if isinstance(value, (dict, list)):
                result[num_key] = process_json(value, current_path)
            else:
                # 处理字符串 hex-> 或特定位置的 hex
                if isinstance(value, str):
                    if value.startswith("hex->"):
                        hex_str = value[5:]
                        if re.fullmatch(r'[0-9a-fA-F]+', hex_str) and len(hex_str) % 2 == 0:
                            result[num_key] = bytes.fromhex(hex_str)
                        else:
                            result[num_key] = value
                    elif len(current_path) >= 2 and current_path[-2] == "5" and current_path[-1] == "2" \
                         and re.fullmatch(r'[0-9a-fA-F]+', value) and len(value) % 2 == 0:
                        result[num_key] = bytes.fromhex(value)
                    else:
                        result[num_key] = value
                else:
                    result[num_key] = value
        return result

    # 基本类型
    return json_obj

def bytes_to_hex(b: Union[bytes, bytearray]) -> str:
    return b.hex()

# 编码函数
def encode(json_obj: Any) -> bytes:
    processed = process_json(json_obj)
    return pb.encode(processed)

# 发送底层函数
async def send(e, cmd: str, content: Any):
    try:
        data = encode(content if isinstance(content, dict) else json.loads(content))
        hex_data = data.hex()
        req = await e.bot.send_api('send_packet', {
            'cmd': cmd,
            'data': hex_data
        })
        # req.data 可能是 bytes 或 hex 字符串
        resp_bytes = req.data if isinstance(req.data, (bytes, bytearray)) else bytes.fromhex(req.data)
        return pb.decode(resp_bytes)
    except Exception as err:
        logger.error(f"sendMessage failed: {err}", exc_info=True)

# 高级接口：Proto, Elem, Long, send_long, recv_long, get_msg
Proto = pb

async def Send(e, cmd: str, content: Any):
    return await send(e, cmd, content)

async def Elem(e, content: Any):
    try:
        packet = {
            "1": {
                "2" if e.is_group else "1": { "1": e.group_id if e.is_group else e.user_id }
            },
            "2": { "1": 1, "2": 0, "3": 0 },
            "3": { "1": { "2": content if isinstance(content, dict) else json.loads(content) } },
            "4": random_uint(),
            "5": random_uint()
        }
        return await Send(e, 'MessageSvc.PbSendMsg', packet)
    except Exception as err:
        logger.error(f"Elem failed: {err}", exc_info=True)

async def send_long(e, content: Any):
    data = {
        "2": {
            "1": "MultiMsg",
            "2": { "1": [ { "3": { "1": content if isinstance(content, dict) else json.loads(content) } } ] }
        }
    }
    compressed = await gzip(encode(data))
    target = int(e.group_id) if e.is_group else e.user_id
    packet = {
        "2": {
            "1": 3 if e.is_group else 1,
            "2": { "2": target },
            "3": str(target),
            "4": compressed
        },
        "15": { "1": 4, "2": 2, "3": 9, "4": 0 }
    }
    resp = await Send(e, 'trpc.group.long_msg_interface.MsgService.SsoSendLongMsg', packet)
    return resp.get("2", {}).get("3")

async def Long(e, content: Any):
    try:
        resid = await send_long(e, content)
        elem = {
            "37": {
                "6": 1,
                "7": resid,
                "17": 0,
                "19": { "15": 0, "31": 0, "41": 0 }
            }
        }
        return await Elem(e, elem)
    except Exception as err:
        logger.error(f"Long failed: {err}", exc_info=True)

async def recvLong(e, resid: Any):
    packet = {
        "1": { "2": resid, "3": True },
        "15": { "1": 2, "2": 0, "3": 0, "4": 0 }
    }
    resp = await Send(e, 'trpc.group.long_msg_interface.MsgService.SsoRecvLongMsg', packet)
    compressed = resp.get("1", {}).get("4", b'')
    data = await gunzip(compressed)
    return pb.decode(data)

async def getMsg(e, message_id: int, is_seq: bool = False):
    seq = message_id if is_seq else (await e.bot.send_api('get_msg', {'message_id': message_id})).real_seq
    if not seq:
        raise RuntimeError("获取 seq 失败，请尝试更新 napcat")
    packet = { "1": { "1": e.group_id, "2": seq, "3": seq }, "2": True }
    return await Send(e, 'trpc.msg.register_proxy.RegisterProxy.SsoGetGroupMsg', packet)
