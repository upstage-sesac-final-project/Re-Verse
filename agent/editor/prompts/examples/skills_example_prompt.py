SKILLS_EXAMPLE_PROMPT = """
{
  "id": 11,
  "name": "파이어볼",
  "description": "적 하나에게 불 속성 마법 데미지를 입힌다.",
  "iconIndex": 64,
  "stypeId": 1,
  "mpCost": 10,
  "tpCost": 0,
  "scope": 1,
  "occasion": 1,
  "speed": 0,
  "successRate": 100,
  "repeats": 1,
  "tpGain": 10,
  "hitType": 0,
  "animationId": 66,
  "damage": {
    "type": 1,
    "elementId": 1,
    "formula": "200 + a.mat * 4",
    "variance": 20,
    "critical": true
  },
  "effects": [],
  "message1": "이(가) 파이어볼을 시전했다!",
  "message2": "",
  "requiredWtypeId1": 0,
  "requiredWtypeId2": 0,
  "note": ""
}
"""
