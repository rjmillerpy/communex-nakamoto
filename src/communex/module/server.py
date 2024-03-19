"""
Server for Commune modules.
"""


from typing import Any, Callable
import re

import fastapi
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from substrateinterface import Keypair  # type: ignore
from keylimiter import KeyLimiter
import starlette.datastructures

from communex.module._ip_limiter import IpLimiterMiddleware
from communex.module import _signer as signer
from communex.module.module import Module, endpoint

def parse_hex(hex_str: str) -> bytes:
    if hex_str[0:2] == '0x':
        return bytes.fromhex(hex_str[2:])
    else:
        return bytes.fromhex(hex_str)


async def peek_body(request: Request) -> bytes:
    """
    Gambiarra to get the body of a request on a middleware, making it available
    to the next handler.
    """
    body = await request.body()

    async def receive():
        return {"type": "http.request", "body": body}
    request._receive = receive  # pyright: ignore [reportPrivateUsage]
    return body


def is_hex_string(string: str):
    # Regular expression to match a hexadecimal string
    hex_pattern = re.compile(r'^[0-9a-fA-F]+$')
    return bool(hex_pattern.match(string))

def _return_error(code: int, message: str):
    return JSONResponse(
        status_code=code, content={
        "error": {
            "code": code,
            "message": message
            }
        }
    )


def _get_headers_dict(headers: starlette.datastructures.Headers, required: list[str]):
    headers_dict: dict[str, str] = {}
    for required_header in required:
        value = headers.get(required_header)
        if not value:
            code = 400
            return False, _return_error(code, f"Missing header: {required_header}")
        headers_dict[required_header] = value
    return True, headers_dict


class ModuleServer:
    def __init__(
            self,
            module: Module,
            key: Keypair,
            max_request_staleness: int=60,
            ip_limiter: KeyLimiter | None=None,
            ) -> None:
        self._module = module
        self._app = fastapi.FastAPI()
        self.key = key
        self.register_endpoints()
        self.register_middleware()
        self._app.add_middleware(IpLimiterMiddleware, limiter=ip_limiter)
        self.max_request_staleness = max_request_staleness
    
    
    def get_fastapi_app(self):
        return self._app

    def register_endpoints(self):
        endpoints = self._module.get_endpoints()
        for name, endpoint_def in endpoints.items():
            class Body(BaseModel):
                params: endpoint_def.params_model  # type: ignore
            def handler(body: Body):
                return endpoint_def.fn(self._module, **body.params.model_dump())  # type: ignore
            self._app.post(f"/method/{name}")(handler)

    def register_middleware(self):
        async def input_middleware(request: Request, call_next: Callable[[Any], Any]):
            body = await peek_body(request)
            required_headers = ['x-signature', 'x-key', 'x-crypto']
            success, headers_dict = _get_headers_dict(request.headers, required_headers)
            if not success:
                error = headers_dict
                return error
            assert isinstance(headers_dict, dict)
            
            signature = headers_dict['x-signature']
            key = headers_dict['x-key']
            crypto = int(headers_dict['x-crypto']) #TODO: better handling of this
            is_hex = is_hex_string(key)
            if not is_hex:
                return _return_error(400, "X-Key should be a hex value")
            signature = parse_hex(signature)
            key = parse_hex(key)
            verified = signer.verify(key, crypto, body, signature)
            if not verified:
                return JSONResponse(
                    status_code=401,
                    content="Signatures doesn't match"
                    )

            response = await call_next(request)
            return response

        self._app.middleware('http')(input_middleware)


def main():
    class Amod(Module):
        @endpoint
        def do_the_thing(self, awesomness: int = 42):
            if awesomness > 60:
                msg = f"You're super awesome: {awesomness} awesomness"
            else:
                msg = f"You're not that awesome: {awesomness} awesomness"
            return {"msg": msg}

    a_mod = Amod()
    keypair = Keypair.create_from_mnemonic(signer.TESTING_MNEMONIC)
    server = ModuleServer(a_mod, keypair)
    app = server.get_fastapi_app()

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)  # type: ignore

if __name__ == "__main__":
    main()
