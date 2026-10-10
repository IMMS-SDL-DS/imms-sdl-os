from prefect import serve
from .zr_btc_synthesis_flow import zr_btc_synthesis_flow
from .solid_dosing_flow import solid_dosing_flow


if __name__ == "__main__":
    serve(
        zr_btc_synthesis_flow.to_deployment(name="zr-btc-sim",  
                                            tags=["sdl", "zr-btc", "sim"], 
                                            description="Zr-BTC MOF 합성 프로토콜 (시뮬레이션)"),
        solid_dosing_flow.to_deployment(name="solid-dosing", 
                                        tags=["sdl", "dosing", "real"],
                                        description="Solid Dosing 프로토콜 (리얼리티)"),
        # 이후 flow 추가 시 여기에 한 줄씩
    )