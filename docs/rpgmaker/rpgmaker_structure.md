# RPG Maker Structure

현재 Re:Verse에서 주로 다루는 RPG Maker 프로젝트 데이터 구조를 간단히 정리한다.

## 기본 경로

- 프로젝트 데이터 루트: `storage/games/{game_id}/data`
- 예시: `storage/games/game_001/data`

## 자주 다루는 파일

- `Actors.json`
- `Classes.json`
- `Enemies.json`
- `Items.json`
- `Skills.json`
- `States.json`
- `System.json`
- `Weapons.json`
- `Map001.json` 같은 맵 파일

## 현재 validator 기준

- 일부 핵심 파일만 schema map에 직접 등록되어 있다.
- 맵 파일은 `Map001.json` 형태를 패턴으로 잡아 `MapFile` 스키마로 검증한다.
- `CommonEvents.json`, `MapInfos.json`, `Tilesets.json`, `Troops.json` 같은 파일은 현재 validator 기준으로 unsupported schema일 수 있다.

## 관련 문서

- validator 실행: [../nodes/validator/test_run.md](../nodes/validator/test_run.md)
- 타일 렌더링 메모: [./rpgmaker_tile_rendering.md](./rpgmaker_tile_rendering.md)
