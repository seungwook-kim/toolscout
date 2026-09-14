# 개발용 로컬 모델 (Ollama)

측정 2026-09-14 · 스크립트 `tests/models/check_local_models.py` · 원자료 `tests/models/local_models.json`
모델 배정은 `models.py`에만 둔다. 이 문서는 VRAM 실측과 선택 근거만 적는다.

## 환경

| 항목 | 값 |
|---|---|
| GPU | NVIDIA GeForce RTX 5070, 총 12,227MiB, 드라이버 616.92 (CUDA 13) |
| 모델을 올리기 전 사용량 | 약 900MiB (Windows 화면 등) |
| Ollama | 0.34.0, Windows 설치 (WSL2는 다운로드 속도가 초당 약 78KB로 Windows의 1/300이라 제외) |
| 서버 환경변수 (사용자 환경변수로 영구) | `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_CONTEXT_LENGTH=8192` |
| 주소 | `http://localhost:11434/v1` (OpenAI 호환, 키 없음). 시작프로그램 `Ollama.lnk`로 로그인 때 자동 시작 |

- OpenAI 호환 API는 요청의 `options.num_ctx`를 무시한다(4096을 보내도 8192 유지). 그래서 num_ctx는 서버 환경변수로 고정한다
- 사고 모델(qwen3)은 `reasoning_effort: none`을 보내야 사고 토큰이 0이 된다. 안 보내면 짧은 답에도 51초가 걸렸다

## VRAM 실측 (num_ctx 8192, 다른 모델을 내린 뒤 한 개씩 올림)

VRAM 증가량 = 올린 뒤 `nvidia-smi` 사용량 - 올리기 전 사용량 (CUDA 컨텍스트 포함). 기준은 9GiB(9,216MiB) 이하, 전부 GPU.

| 모델 (Q4_K_M) | VRAM 증가량 | 올린 뒤 GPU 전체 | Ollama size_vram | 전부 GPU | 첫 로드 | 선별 20건 JSON | 생성 속도 | 도구 호출 | 결과 |
|---|---|---|---|---|---|---|---|---|---|
| qwen3:8b | 6,213MiB (6.07GiB) | 7,105MiB | 6,003MiB | 예 | 6.1초 | 9.8초, 규격 맞음 | 104 tok/s | 지원 | 8GiB 미만 |
| llama3.1:8b | 5,820MiB (5.68GiB) | 6,738MiB | 5,659MiB | 예 | 5.7초 | 7.9초, 규격 맞음 | 110 tok/s | 지원 | 8GiB 미만 |
| **gemma3:12b** | **9,173MiB (8.96GiB)** | 10,097MiB | 7,676MiB | 예 | 24.5초 | 18.2초, 규격 맞음 | 66 tok/s | **미지원** | **기본 (8~9GiB 안에서 가장 큼)** |
| qwen3:14b | 10,053MiB (9.82GiB) | 10,973MiB | 9,843MiB | 예 | 20.7초 | 17.7초, 규격 맞음 | 61 tok/s | 지원 | 9GiB 초과, 삭제 |

## 한글 응답 ("다음 영문 제목을 한 줄 한글로 요약", 3건)

| 모델 | OpenAI adds structured outputs to the Realtime API for voice agents | Hugging Face releases a small open-weight model that runs coding agents on a laptop | n8n ships a native MCP client node so workflows can call external AI tools |
|---|---|---|---|
| qwen3:8b | 오픈AI, 음성 에이전트용 실시간 API에 구조화된 출력 기능 추가 | 허깅페이스, 랩탑에서 코드 에이전트를 실행할 수 있는 소형 오픈웨이트 모델 발표 | n8n은 외부 AI 도구를 호출할 수 있는 네이티브 MCP 클라이언트 노드를 제공합니다. |
| llama3.1:8b | 오픈 AI, 실시간 API에 음성 에이전트에 대한 구조화된 출력 추가 | 휴징페이스(Hugging Face)가 코드 작성 에이전트를 노트북에서 작동하는 작은 오픈 가중치 모델을 출시했다. | n8n은 MCP 클라이언트 노드(native client node)를 내장하여 워크플로우가 외부 AI 도구를 호출할 수 있다. |
| gemma3:12b | OpenAI가 음성 에이전트를 위한 실시간 API에 구조화된 출력 기능을 추가했습니다. | Hugging Face에서 노트북에서도 코딩 에이전트를 실행할 수 있는 소형 오픈 웨이트 모델을 출시했습니다. | n8n은 워크플로우에서 외부 AI 도구를 호출할 수 있도록 기본 MCP 클라이언트 노드를 제공합니다. |
| qwen3:14b | 오픈AI, 음성 에이전트를 위한 실시간 API에 구조화된 출력 기능 추가 | 허깅페이스, 노트북에서도 작동하는 소형 오픈웨이트 모델 출시 | n8n은 외부 AI 도구를 호출할 수 있는 네이티브 MCP 클라이언트 노드를 제공합니다. |

- llama3.1:8b는 고유명사 표기("휴징페이스")와 문장 구조가 어색하다. gemma3:12b는 제품명을 원문대로 두고 문장이 가장 자연스럽다

## 선택

| 역할 | 개발 모드 제공자 순서 | 근거 |
|---|---|---|
| 큐레이터·게이트 (JSON만) | ollama `gemma3:12b` → groq → gemini → openrouter | 8~9GiB 안에서 가장 큰 모델. 선별 20건 JSON 규격을 지킴 |
| 해설가·검증관 (도구 호출) | groq → gemini → openrouter | gemma3:12b가 도구 호출을 지원하지 않아 로컬을 쓰지 않는다 (2026-09-14 사용자 결정) |

## 주의

- gemma3:12b는 올린 뒤 GPU 전체 사용량이 10,097MiB로, 12GB 중 약 1.9GiB가 남는다. 다른 GPU 프로그램을 같이 쓰면 일부가 CPU로 밀릴 수 있다
- 첫 로드가 24.5초라 30초 타임아웃에 가깝다. 30분 넘게 쉬어 모델이 내려간 뒤 첫 호출은 타임아웃으로 다음 제공자로 넘어갈 수 있다
- qwen3:8b·llama3.1:8b는 기준 밖이지만 9GiB 이하라 지우지 않았다 (합계 약 10GB 디스크)
