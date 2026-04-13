import json
import os
from pathlib import Path

# __file__ 기준으로 경로 계산 (agent/generation/mapgen/ → agent/)
_AGENT_DIR = Path(__file__).parents[2]
map_folder = _AGENT_DIR / "rag/data/samplemaps"
output_file = _AGENT_DIR / "rag/data/all_maps_info.json"

all_maps_data = []

if not map_folder.exists():
    print(f"경로를 찾을 수 없습니다: {map_folder}")
else:
    for file_name in sorted(os.listdir(map_folder)):
        if file_name.startswith("Map") and file_name.endswith(".json"):
            file_path = map_folder / file_name

            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)

                    # RAG 분석용 핵심 데이터 추출
                    map_summary = {
                        "fileName": file_name,
                        "displayName": data.get("displayName", ""),
                        "width": data.get("width", 0),
                        "height": data.get("height", 0),
                        "tilesetId": data.get("tilesetId", 0),
                        "bgmName": data.get("bgm", {}).get("name", ""),  # 음악으로 분위기 파악
                        "note": data.get("note", ""),
                        "encounterCount": len(data.get("encounterList", [])),
                    }
                    all_maps_data.append(map_summary)
            except Exception as e:
                print(f"{file_name} 처리 중 오류: {e}")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_maps_data, f, ensure_ascii=False, indent=2)

    print(f"완료! {len(all_maps_data)}개의 맵 정보가 {output_file}에 저장되었습니다.")
