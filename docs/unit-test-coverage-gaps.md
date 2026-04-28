# Unit test coverage gaps (exhaustive inventory)

Generated: **2026-04-28** (source: `coverage-unit.json`).

Every `mindtrace/*` path below appears in `.coveragerc` `source` and had at least one **statement** not executed by a full **`tests/unit/mindtrace`** run. Ranges are **statement lines** from coverage.py (compressed).

## Summary

- **Files with gaps:** 121
- **Total missing statements:** 5302

## Regenerate

```bash
uv run coverage erase
uv run coverage run --rcfile=.coveragerc --parallel-mode -m pytest -q \
  --rootdir="$PWD" -W ignore::DeprecationWarning tests/unit/mindtrace
uv run coverage combine
uv run coverage json -o coverage-unit.json
uv run python scripts/generate_unit_coverage_gaps.py coverage-unit.json
```

## Exhaustive per-file gap list

| File | Missing | Line ranges | Tier | Note |
|---:|---:|---|:---:|---|
| `mindtrace/agents/mindtrace/agents/_function_schema.py` | 46 | 15, 17, 23-27, 33-36, 47, 52, 57, 59-62, 64-65, 67-70, 72-73, 75-78, 80, 95-96, 102-103, 114, 135-136, 140-141, 150, 182-183, 192-193, 197 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/_tool_manager.py` | 5 | 28, 32-33, 45, 55 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/core/abstract.py` | 9 | 21, 26, 31, 36, 41, 51, 70, 74, 78 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/core/base.py` | 61 | 88-89, 91, 165, 190, 201, 214, 232, 237-241, 253, 257, 277-279, 296, 303, 305, 307, 316-318, 327-331, 341-347, 364, 383-385, 395-398, 419, 428-430, 439, 442-445, 462, 464, 468-472 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/core/wrapper.py` | 1 | 57 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/execution/_queue.py` | 4 | 29, 34, 39, 44 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/execution/local.py` | 2 | 49-50 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/execution/rabbitmq.py` | 20 | 16-17, 87, 107-111, 113-120, 122-123, 131-132 | **B** | `serve()` long-poll; keep async mocks only. |
| `mindtrace/agents/mindtrace/agents/history/__init__.py` | 3 | 15, 19, 23 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/memory/_store.py` | 5 | 20, 24, 28, 32, 36 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/memory/toolset.py` | 1 | 52 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/models/_model.py` | 12 | 50, 54-59, 64, 69, 73, 82, 91 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/models/openai_chat.py` | 3 | 23-24, 190 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/profiles/__init__.py` | 8 | 33-35, 38-41, 46 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/prompts.py` | 1 | 64 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/providers/_provider.py` | 5 | 19, 24, 29, 32, 35 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/providers/gemini.py` | 2 | 10-11 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/providers/ollama.py` | 2 | 10-11 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/providers/openai.py` | 2 | 10-11 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/toolsets/_toolset.py` | 2 | 24, 34 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/agents/mindtrace/agents/toolsets/mcp.py` | 2 | 70, 91 | **B** | Agents: providers and runtime; mock LLM I/O. |
| `mindtrace/automation/mindtrace/automation/label_studio/label_studio_api.py` | 33 | 80-81, 85-89, 91, 126, 172, 194-195, 307, 606-608, 713, 731, 758, 814, 826-828, 830-832, 868, 870-873, 875-876 | **B** | HTTP workers; narrow client mocks. |
| `mindtrace/automation/mindtrace/automation/workers/pipeline_worker.py` | 1 | 102 | **B** | HTTP workers; narrow client mocks. |
| `mindtrace/cluster/mindtrace/cluster/core/cluster.py` | 82 | 94-97, 100-102, 372-374, 411-412, 575-576, 783-786, 809-810, 870, 936-941, 955-956, 958, 960, 964, 972-975, 978-979, 981-984, 987-993, 996-998, 1046-1047, 1051, 1060, 1075-1076, 1080-1081, 1084, 1114-1120, 1130-1131, 1134, 1144-1145, 1148, 1158-1159, 1162, 1168-1169, 1175-1176, 1351 | **B** | Subprocess/docker/git; mock tooling. |
| `mindtrace/cluster/mindtrace/cluster/workers/environments/git_env.py` | 14 | 34, 146, 160, 176-177, 196, 233, 235, 239-241, 243, 245-246 | **B** | Subprocess/docker/git; mock tooling. |
| `mindtrace/database/mindtrace/database/backends/mongo_odm.py` | 35 | 218-220, 700-701, 703-704, 706-712, 714-718, 720, 735-736, 738-739, 741-745, 757, 792-793, 797-798, 800 | **B** | ODM; use test doubles for error paths. |
| `mindtrace/datalake/mindtrace/datalake/service.py` | 4 | 467, 469, 1093, 1103 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/datalake/mindtrace/datalake/sync.py` | 2 | 317, 558 | **B** | Prefer unit tests on pure merge/diff helpers; rest is I/O. |
| `mindtrace/hardware/mindtrace/hardware/__init__.py` | 2 | 89, 91 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/__init__.py` | 11 | 25-26, 32-33, 35-36, 38-40, 50, 67 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/backends/basler/__init__.py` | 3 | 45-47 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/backends/basler/basler_camera_backend.py` | 431 | 250, 293, 305-306, 308, 310, 312-313, 315-317, 320, 323, 326-330, 332, 334, 336-338, 340, 357-361, 390, 393, 413, 415, 417, 419-421, 424-425, 428-429, 431, 433, 436-440, 443-444, 447-448, 451-452, 454-455, 457-459, 519-521, 524-528, 530-533, 535, 537-539, 544-545, 548-549, 551-552, 554-556, 558-560, 607-608, 651-652, 666-667, 675-677, 679, 701-702, 704-705, 708, 710-711, 713-714, 718, 720, 722-723, 726-727, 730-731, 734-735, 740, 743-744, 749, 752-753, 756, 759, 763, 768-770, 773-774, 776, 779, 781, 784-785, 787, 789, 792, 795-796, 799, 802-803, 806, 808-809, 814, 816-818, 829-830, 832, 864-865, 868-869, 945, 1029, 1081, 1101, 1117, 1119, 1219, 1225-1226, 1231, 1388-1390, 1399-1405, 1408-1414, 1417-1419, 1424-1426, 1429-1431, 1436-1438, 1443-1446, 1451-1453, 1461, 1509-1510, 1513, 1516-1517, 1523-1524, 1536-1537, 1580-1583, 1635, 1637, 1669, 1729, 1743-1745, 1755, 1777-1779, 1793, 1810-1811, 1813-1815, 1818, 1840, 1849-1851, 1855-1856, 1858, 1871, 1888-1889, 1891, 1896-1897, 1899-1900, 1902-1903, 1905, 1909-1910, 1913-1914, 1916, 1919, 1921-1922, 1924-1926, 1930-1931, 1933-1934, 1936-1937, 1940-1941, 1943-1944, 1948-1949, 1951, 1953-1955, 1959-1960, 1962-1963, 1965-1967, 1969-1970, 1972-1974, 1978-1979, 1981-1982, 1984-1986, 1988, 1990-1992, 1996-1997, 1999-2000, 2002-2004, 2006-2007, 2009-2011, 2015-2016, 2018-2019, 2021-2023, 2025, 2027-2029, 2040-2041, 2043-2044, 2052, 2121, 2135-2137, 2156, 2180, 2222, 2263, 2281, 2290, 2294, 2300, 2313, 2324-2325, 2327-2330, 2332-2333, 2336, 2339, 2341, 2343-2345, 2353-2354, 2356-2359, 2361-2364, 2366, 2368-2370, 2378-2379, 2381-2384, 2386-2389, 2391, 2393-2395, 2417-2418, 2438-2439, 2444-2445, 2448-2452, 2457, 2463-2466, 2471, 2485-2486, 2491, 2499-2502, 2552, 2554, 2559-2562, 2579, 2592-2593, 2612-2613, 2617-2618, 2634-2636, 2641-2642, 2646-2648 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/backends/basler/mock_basler_camera_backend.py` | 31 | 212-213, 848, 851, 856, 859, 861-862, 868, 874, 887, 995-996, 998, 1009, 1011-1012, 1015-1016, 1019-1020, 1023-1025, 1028-1030, 1032-1035 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/backends/camera_backend.py` | 77 | 131-133, 137-138, 141-144, 155-156, 158, 161, 163-164, 262, 266, 270, 274, 287, 291, 295, 300, 343-344, 347-348, 351-352, 355-356, 359-360, 363-364, 367-368, 371-372, 375-376, 379-380, 383-384, 389-390, 394-395, 399-400, 404-405, 409-410, 414-415, 426-427, 435-436, 448-449, 453-454, 462-463, 467-468, 479-480, 489-490, 498-499, 516-517 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/backends/genicam/genicam_camera_backend.py` | 272 | 15-16, 19-22, 122, 147, 149, 153, 156, 204-207, 246, 257, 279, 295, 298, 300, 302-303, 305, 307, 309, 311-315, 317-324, 326, 337, 339-340, 372, 386, 395, 434, 440, 467-468, 470-471, 477-478, 480-481, 496-497, 511, 513, 566, 579, 621, 653-655, 657, 688, 692-694, 696, 724-726, 740-741, 755, 770-771, 774, 779-781, 794, 800-802, 816, 832, 838-840, 863, 867-869, 882, 891, 897-899, 912, 921, 927-929, 952, 957-959, 982, 999, 1015, 1039-1040, 1042, 1044, 1050-1052, 1066, 1079-1080, 1100-1102, 1127-1131, 1155, 1178, 1187-1188, 1231-1232, 1236, 1240, 1246-1248, 1265-1271, 1285, 1297-1300, 1309-1311, 1333-1334, 1339-1340, 1344-1346, 1365, 1368-1369, 1377-1378, 1386, 1392-1393, 1405, 1419, 1421, 1424-1425, 1428-1433, 1435, 1439-1441, 1454, 1467, 1469, 1471, 1475-1476, 1479-1485, 1487, 1492-1494, 1506, 1529, 1531-1532, 1535, 1539-1541, 1555, 1562, 1574, 1598-1602, 1615, 1654-1658, 1680-1681, 1690-1691, 1726-1727, 1733-1735, 1752, 1770-1771, 1776-1777, 1782-1783, 1788-1789, 1796-1798, 1810, 1829-1830, 1837-1838, 1845-1846, 1853-1854, 1860-1862, 1872, 1886-1887, 1893-1894, 1903-1904, 1912-1913, 1920-1922 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/backends/opencv/__init__.py` | 3 | 33-35 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/backends/opencv/opencv_camera_backend.py` | 131 | 17-19, 165-166, 183-184, 186-188, 331, 360, 382-384, 386-387, 389-397, 399-405, 407-411, 413-417, 419-425, 427-434, 436-443, 445-446, 452, 454, 456-461, 463, 465-466, 469-470, 472-477, 479-480, 482-491, 496-497, 506-507, 509-511, 526, 723-724, 729-730, 733, 814, 1101-1102, 1221-1223, 1246-1247, 1257-1259, 1321-1322, 1324-1325, 1333, 1341, 1352, 1354 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/core/async_camera.py` | 130 | 66, 78, 82, 84-85, 87-88, 90-91, 93, 97, 105, 109, 117, 121-122, 173-174, 183, 279-280, 295, 312, 330, 332, 334, 400-401, 409, 557, 565-566, 577, 585-586, 597, 605-606, 616, 620, 624-625, 633-637, 648-649, 653, 657-658, 671-673, 675, 686-690, 701-705, 716-720, 731-735, 746-750, 758-760, 762, 782, 794-796, 798-799, 803-811, 864-865, 893, 897-901, 912-913, 916, 920-921, 944-946, 951-952, 956-957, 961-962, 966-967, 971-972, 976-977, 986-987 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/core/async_camera_manager.py` | 176 | 159-160, 180-181, 190-191, 195-196, 213-214, 219-220, 244, 265, 315, 329-333, 354, 357-359, 361-364, 366-369, 371-372, 374-375, 377-385, 393, 420, 451-452, 459, 482-487, 530, 542, 554-556, 558-563, 572, 584-586, 588-591, 630-632, 634-637, 641-644, 648, 663, 669-670, 674-685, 689, 692-696, 698, 703, 706-709, 712-714, 716-720, 722, 727, 737, 750, 760-761, 829, 840-841, 850, 897, 901, 906-907, 919-922, 955-956, 1002-1006, 1009, 1022, 1024-1029, 1031, 1034-1035, 1040-1041, 1043-1045, 1052, 1080-1081, 1083-1089, 1107-1109 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/core/camera.py` | 7 | 356, 360, 368, 376, 387, 391, 395 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/core/capture_groups.py` | 59 | 43, 48, 52, 78-79, 82, 84-86, 88-89, 91-93, 95-96, 98-99, 101-102, 104-105, 107-109, 111-113, 116-122, 124, 141-142, 144-147, 149, 155, 157-161, 163, 195-196, 198-200, 203, 205, 211-212 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/homography/calibrator.py` | 18 | 275-276, 280, 286, 392, 394, 423, 425, 567, 586, 590, 602, 604, 609, 619, 624-626 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/homography/measurer.py` | 1 | 338 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cameras/setup/setup_basler.py` | 40 | 105-107, 148, 155, 168, 176, 183, 185-187, 189-192, 194, 226, 346-349, 365-366, 369-370, 392, 397-398, 424, 439-440, 453-454, 456-457, 488-490, 549, 557 | **C** | Device/setup scripts; unit-test only extracted pure helpers. |
| `mindtrace/hardware/mindtrace/hardware/cameras/setup/setup_cameras.py` | 11 | 160-161, 252-254, 300-302, 390, 435, 439 | **C** | Device/setup scripts; unit-test only extracted pure helpers. |
| `mindtrace/hardware/mindtrace/hardware/cameras/setup/setup_genicam.py` | 38 | 215-216, 220-222, 307-308, 313-315, 381, 393-394, 397-398, 431-432, 445-448, 450-451, 482-484, 492-494, 522-524, 582, 601, 606, 633, 640, 644 | **C** | Device/setup scripts; unit-test only extracted pure helpers. |
| `mindtrace/hardware/mindtrace/hardware/cli/__main__.py` | 26 | 95, 97, 99, 125-126, 129-130, 133-134, 138, 148-149, 154-158, 164-165, 167-172, 176 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cli/commands/camera.py` | 60 | 26-27, 30-35, 38-40, 42, 44-45, 48-54, 56-58, 61-62, 64-66, 68, 70-71, 77-78, 80, 82-84, 86, 92, 95-96, 98-101, 103-104, 107-114, 120, 123-125 | **B** | Typer CliRunner + mocks (scanner historically imported missing `cli.utils.network`). |
| `mindtrace/hardware/mindtrace/hardware/cli/commands/plc.py` | 52 | 22-23, 26-31, 34-36, 38, 40-41, 44-50, 52-54, 56-57, 63-64, 66, 69-71, 73, 79, 82-83, 85-88, 90-91, 94-99, 105, 109-111 | **B** | Typer CliRunner + mocks (scanner historically imported missing `cli.utils.network`). |
| `mindtrace/hardware/mindtrace/hardware/cli/commands/scanner.py` | 58 | 28-29, 32-37, 40-42, 44, 46-47, 50-56, 58-60, 63-66, 68, 70-71, 77-78, 80, 82-84, 86, 92, 95-96, 98-101, 103-104, 107-113, 119, 121-123 | **B** | Typer CliRunner + mocks (scanner historically imported missing `cli.utils.network`). |
| `mindtrace/hardware/mindtrace/hardware/cli/commands/status.py` | 40 | 11, 14, 17-20, 22-28, 30, 33-35, 38-40, 42-44, 46-48, 50-52, 54-58, 61-62, 64, 66-68 | **B** | Typer CliRunner + mocks (scanner historically imported missing `cli.utils.network`). |
| `mindtrace/hardware/mindtrace/hardware/cli/commands/stereo.py` | 58 | 28-29, 32-37, 40-42, 44, 46-47, 50-56, 58-60, 63-66, 68, 70-71, 77-78, 80, 82-84, 86, 92, 95-96, 98-101, 103-104, 107-113, 119, 121-123 | **B** | Typer CliRunner + mocks (scanner historically imported missing `cli.utils.network`). |
| `mindtrace/hardware/mindtrace/hardware/cli/core/logger.py` | 3 | 91, 99, 115 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cli/core/process_manager.py` | 24 | 79, 81, 140, 142, 165, 191, 193, 224, 250, 252, 283, 321, 323-326, 337, 341-342, 380, 384, 390-391, 409 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/cli/utils/display.py` | 53 | 19-21, 24-30, 32, 34, 37-39, 41-42, 45, 48, 51, 54, 56, 58, 68-70, 72-73, 76, 78-79, 81-82, 84, 94-95, 97-99, 101-102, 104, 106, 108, 110, 112, 117, 121-122, 133-134, 136-137 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/core/config.py` | 125 | 631, 634-636, 639-640, 642, 645-648, 651-654, 680, 683, 686-689, 693, 704-707, 710-713, 716, 720, 723-726, 736, 908-911, 914-917, 920-923, 926-927, 930, 933-936, 939-942, 945-946, 949-952, 955-958, 961-962, 965-968, 971-974, 977-980, 983, 986-989, 993, 996, 999-1002, 1006-1009, 1012, 1015-1018, 1021-1024, 1027-1028, 1031-1034, 1037-1040, 1043-1046, 1126, 1128, 1142 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/plcs/backends/__init__.py` | 2 | 13-14 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/plcs/backends/allen_bradley/allen_bradley_plc.py` | 19 | 28-33, 373-375, 515-517, 527-528, 1007-1008, 1025-1026, 1038 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/plcs/backends/allen_bradley/mock_allen_bradley.py` | 14 | 259, 281, 347-350, 352, 356, 371-373, 428, 700-701 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/plcs/backends/base.py` | 16 | 157-158, 160, 163, 165-166, 178, 188, 198, 208, 221, 234, 244, 257, 268, 279 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/plcs/plc_manager.py` | 11 | 221-222, 231-232, 368, 411-413, 600-602 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/scanners_3d/backends/photoneo/photoneo_backend.py` | 207 | 46, 166, 191-193, 195-196, 199, 214-216, 218, 243-244, 264, 284-285, 294, 304, 308, 310-313, 315-316, 325, 337, 365-369, 375, 406-408, 412, 414, 416-417, 419, 422-426, 429-434, 436-437, 439-440, 628, 645, 666, 670, 678, 700-701, 715, 735-736, 741-742, 747-748, 753-754, 759-760, 765-766, 771-772, 777-778, 783-784, 805-806, 809-810, 813-814, 817-818, 823-824, 827-828, 831-832, 835-836, 839-840, 845-846, 849-850, 855-856, 859-860, 865-866, 869-870, 875-876, 879-880, 883-884, 887-888, 896-898, 901-902, 905-906, 923-924, 927-930, 933-936, 939-942, 946-949, 952-955, 958-961, 964-967, 970-973, 983-986, 992-993, 996-999, 1003-1006, 1009-1012, 1016-1019, 1022-1025, 1028-1031, 1034-1037, 1046-1049, 1054-1055, 1060-1061, 1392, 1407-1408 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/scanners_3d/backends/scanner_3d_backend.py` | 41 | 153, 203, 240, 252, 262, 371, 381, 385, 397, 401, 409, 413, 421, 425, 437, 441, 449, 453, 465, 469, 481, 485, 493, 497, 509, 513, 521, 525, 533, 537, 545, 549, 561, 573, 577, 585, 589, 601, 605, 634-635 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/scanners_3d/core/models.py` | 37 | 173-174, 307, 309, 311, 486, 488-489, 491-492, 494-495, 497, 499-501, 503-507, 509-512, 514-515, 517-518, 520-522, 524-526, 580, 582 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/scanners_3d/core/scanner_3d.py` | 2 | 75-76 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/scanners_3d/setup/__init__.py` | 2 | 3, 10 | **C** | Device/setup scripts; unit-test only extracted pure helpers. |
| `mindtrace/hardware/mindtrace/hardware/scanners_3d/setup/setup_photoneo.py` | 540 | 24-33, 35, 37-38, 41, 49, 61-62, 64-67, 70, 93, 99, 101-106, 112, 126-127, 129, 140-141, 143-147, 149-153, 155-163, 166-168, 170, 172-177, 179-184, 186-189, 191, 197, 206-216, 219-222, 225-229, 231, 233, 239, 241-246, 249-252, 254-255, 257, 263, 265-270, 272-273, 275, 281-282, 284-289, 295, 301-303, 305-306, 308, 310, 312, 318-319, 321-322, 324-325, 327, 339-341, 343-345, 347, 353-354, 357-361, 363-368, 374, 380-381, 383-384, 386-387, 389-392, 394, 396-398, 400-401, 403, 405-409, 411, 421, 428-429, 439-442, 444-445, 447-449, 455, 461-462, 464-469, 471-473, 475, 481, 484-485, 487-488, 490-491, 494, 497-498, 500-502, 506, 510, 514-517, 520-522, 525-528, 532-535, 541-543, 545, 547-554, 556, 562, 565-566, 568-570, 572-575, 578, 580-581, 584-585, 587-591, 594-596, 599-601, 603-605, 607, 613, 616, 618-619, 622-625, 632-635, 637-640, 642, 645-647, 649-659, 661-663, 665-670, 673-675, 678-680, 683-684, 686-688, 690, 692-693, 695, 701, 703-704, 706, 709-712, 714, 720, 726, 728-733, 735-736, 738, 744-745, 747-751, 754-758, 761-764, 767-769, 771-772, 774, 776, 778-782, 784, 790, 793, 798-806, 809-810, 823-827, 830-834, 837-838, 840, 842, 848-849, 852, 856-860, 862-863, 866-870, 873-874, 876-877, 879, 881, 883-885, 891, 897-898, 900, 903-904, 906-907, 910-911, 913-914, 917-918, 920, 923, 931, 933-934, 937, 939-940, 943, 945-946, 954-955, 963, 965-966, 968-969, 972-973, 977, 979-980, 982-983, 986-987, 991, 993-994, 996, 998-999, 1001-1002, 1004, 1007-1008, 1013, 1015-1016, 1018, 1021-1023, 1025, 1027-1030, 1032-1041, 1043-1044, 1046, 1048-1053, 1055-1062, 1064, 1067, 1069, 1072-1073 | **C** | Device/setup scripts; unit-test only extracted pure helpers. |
| `mindtrace/hardware/mindtrace/hardware/sensors/backends/mqtt.py` | 6 | 16-17, 222, 236-237, 239 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/sensors/core/manager.py` | 2 | 178-179 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/sensors/simulators/base.py` | 4 | 30, 39, 61, 71 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/sensors/simulators/mqtt.py` | 2 | 15-16 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/services/__init__.py` | 6 | 25, 27, 35, 37, 40, 42 | **B** | Services: FastAPI/Discord/etc.; TestClient + mocks. |
| `mindtrace/hardware/mindtrace/hardware/services/cameras/connection_manager.py` | 7 | 423-425, 433-434, 442-443 | **B** | HTTP polling/client code; mock transport. |
| `mindtrace/hardware/mindtrace/hardware/services/cameras/launcher.py` | 16 | 3-4, 6, 9, 11-14, 16, 18-19, 22, 26, 34, 37-38 | **B** | Services: FastAPI/Discord/etc.; TestClient + mocks. |
| `mindtrace/hardware/mindtrace/hardware/services/cameras/models/requests.py` | 18 | 76, 84, 191, 193, 236, 241-243, 245, 439, 476, 481, 489, 495, 538, 577, 580, 587 | **A** | Pydantic models; validation and defaults. |
| `mindtrace/hardware/mindtrace/hardware/services/cameras/service.py` | 288 | 426-428, 442-444, 456, 458-460, 462-463, 468-469, 474, 476, 508-510, 525-527, 531-532, 535-537, 539-548, 550, 558, 563-565, 569-572, 574, 576-580, 591-593, 603, 621-623, 673, 680, 693, 701, 754-756, 782, 805, 829-831, 840, 853-854, 859-860, 869-870, 879-880, 889-890, 894-895, 904-905, 924-926, 1022, 1164-1166, 1190, 1196, 1258, 1264, 1292-1294, 1324-1326, 1360, 1367-1368, 1373, 1417, 1442-1443, 1447-1449, 1454-1458, 1463-1468, 1472-1476, 1481-1483, 1487-1490, 1495-1497, 1545-1546, 1548, 1568-1569, 1572, 1588, 1614-1616, 1626-1628, 1637-1639, 1643-1644, 1647, 1650-1651, 1653, 1658, 1660, 1663-1665, 1667, 1670, 1672, 1674-1675, 1678-1681, 1683, 1686-1688, 1690-1691, 1693, 1698, 1700, 1703-1704, 1707, 1711, 1713-1714, 1717, 1719-1721, 1727-1728, 1734, 1738-1739, 1742-1743, 1745-1746, 1748-1750, 1752-1753, 1755, 1765-1767, 1769, 1774-1775, 1778-1779, 1781-1782, 1784, 1790, 1795-1797, 1801-1802, 1804-1805, 1807-1808, 1810, 1815-1817, 1821-1822, 1824-1825, 1827-1828, 1830, 1835-1837, 1841-1842, 1844-1845, 1847-1848, 1850, 1855-1859, 1863-1864, 1866-1867, 1869-1870, 1872, 1877-1879, 1883-1884, 1886-1887, 1889, 1892-1893, 1904-1906, 1908-1909, 1915, 1917, 1922-1924, 1947, 2166-2169 | **B** | FastAPI: TestClient + dependency overrides. |
| `mindtrace/hardware/mindtrace/hardware/services/plcs/connection_manager.py` | 59 | 40-44, 48-52, 61-62, 70-71, 82-84, 115, 126-127, 138-140, 151-153, 164-166, 174-175, 183-184, 197-199, 211-213, 224-226, 239-241, 252-254, 266-268, 280-282, 293-295, 303-304 | **B** | HTTP polling/client code; mock transport. |
| `mindtrace/hardware/mindtrace/hardware/services/plcs/launcher.py` | 13 | 3-4, 6, 9, 11-13, 15, 18, 21, 28, 31-32 | **B** | Services: FastAPI/Discord/etc.; TestClient + mocks. |
| `mindtrace/hardware/mindtrace/hardware/services/plcs/models/requests.py` | 6 | 74, 96, 99, 101, 120, 141 | **A** | Pydantic models; validation and defaults. |
| `mindtrace/hardware/mindtrace/hardware/services/plcs/service.py` | 225 | 70, 77, 85-86, 89-90, 93, 97-103, 107-111, 113-114, 119, 122, 125, 128-129, 132-133, 136, 139, 144-149, 152-154, 163, 168-171, 173-176, 180-182, 185-187, 197, 200-202, 206-208, 211-214, 216, 222-224, 229-230, 233, 246, 248, 251-253, 257-261, 263-264, 266, 279-282, 284-289, 291, 299, 304-306, 310-312, 314-317, 321-323, 326-328, 330, 338, 343-345, 349-352, 354-357, 361-363, 365-368, 373-375, 377, 379-383, 387-389, 391, 393-394, 397-399, 403-405, 407-408, 410, 417-419, 423-425, 427-428, 430, 437-439, 443-445, 447-450, 454-455, 458-459, 462-463, 465, 473, 476-478, 483-485, 487, 498-501, 505-507, 509, 524-527, 532-534, 536-537, 540-541, 543, 545, 554, 557-559, 564-568, 570, 577-579 | **B** | FastAPI: TestClient + dependency overrides. |
| `mindtrace/hardware/mindtrace/hardware/services/scanners_3d/connection_manager.py` | 63 | 40-44, 48-52, 57-58, 62-63, 67-69, 74-76, 80-82, 86-88, 92-94, 98-99, 103-104, 109-111, 115-117, 122-124, 128-130, 134-136, 153, 165-166, 170-172, 185, 193-194, 200-202, 207-208, 212 | **B** | HTTP polling/client code; mock transport. |
| `mindtrace/hardware/mindtrace/hardware/services/scanners_3d/launcher.py` | 13 | 3-4, 6, 9, 11-13, 15, 18, 21, 28, 31-32 | **B** | Services: FastAPI/Discord/etc.; TestClient + mocks. |
| `mindtrace/hardware/mindtrace/hardware/services/scanners_3d/service.py` | 304 | 95, 102, 105-107, 110, 119, 125, 128, 131, 138, 141-142, 145-146, 149, 152, 161-163, 172, 178-179, 185, 193-194, 199, 202, 215-217, 225-226, 239-245, 249-250, 254, 257-259, 266-267, 275, 279, 281-289, 291, 299, 301-302, 304-309, 313, 315-324, 326, 334, 336-337, 339-344, 348, 350-359, 361, 369-370, 372-380, 382, 388, 398, 400-401, 403-404, 406, 408, 412, 414-415, 417-419, 421, 423, 427-428, 430, 438, 446, 448-449, 451-453, 456, 478-480, 484, 486-487, 489-490, 493, 504, 507-514, 517-526, 529-532, 535-538, 541-544, 547-554, 557-562, 564, 566-568, 572, 574-577, 580-581, 583-587, 589, 597, 599-600, 602-604, 607, 643-645, 653, 655-656, 658-659, 661, 670, 673, 675-676, 678-679, 681-682, 684, 686-687, 689-690, 692, 708-710, 714-717, 719-723, 725-726, 728, 730, 739, 741, 749-753, 755, 757, 767, 769-770, 772-773, 775, 780, 783-784, 787-788, 790, 802-804, 808-811, 813-817, 819-820, 822, 824, 829, 831, 838-842, 844, 846 | **B** | FastAPI: TestClient + dependency overrides. |
| `mindtrace/hardware/mindtrace/hardware/services/sensors/launcher.py` | 13 | 3-4, 6, 9, 11-13, 15, 18, 21, 28, 31-32 | **B** | Services: FastAPI/Discord/etc.; TestClient + mocks. |
| `mindtrace/hardware/mindtrace/hardware/services/sensors/service.py` | 17 | 284-293, 298-301, 308-310 | **B** | FastAPI: TestClient + dependency overrides. |
| `mindtrace/hardware/mindtrace/hardware/services/stereo_cameras/connection_manager.py` | 62 | 40-44, 48-52, 57-58, 62-63, 67-69, 74-76, 80-82, 86-88, 92-94, 98-99, 103-104, 109-111, 115-117, 121-122, 127-129, 133-135, 139-141, 156, 166-167, 171-173, 184, 191-192, 198-200 | **B** | HTTP polling/client code; mock transport. |
| `mindtrace/hardware/mindtrace/hardware/services/stereo_cameras/launcher.py` | 13 | 3-4, 6, 9, 11-13, 17, 20, 23, 30, 33-34 | **B** | Services: FastAPI/Discord/etc.; TestClient + mocks. |
| `mindtrace/hardware/mindtrace/hardware/services/stereo_cameras/service.py` | 341 | 91, 98, 101, 104-106, 109, 118, 124, 127, 130, 137, 142-143, 146-147, 150, 153, 162, 165-166, 175, 178, 184, 192, 195, 200, 206, 214-216, 219, 222, 229-231, 238-240, 248-254, 261-265, 269-270, 279-281, 285-286, 288-291, 298-299, 301-302, 305-306, 308-310, 314-316, 318-324, 326-330, 332-333, 339-340, 342-343, 345-346, 348-350, 354-356, 358-364, 366-370, 372-373, 379-385, 389-390, 399-402, 404, 407, 409, 417-419, 423-426, 428, 431, 434, 436-438, 444, 453-455, 459-461, 463, 465-466, 468, 470, 485-488, 492, 494-495, 497, 504, 511-514, 516, 519, 521, 523, 525-528, 532-534, 536-539, 541-547, 549-550, 556-559, 561, 564-571, 573, 584-586, 593-596, 598, 601, 608, 611-612, 614, 616-617, 619, 621, 631-633, 637-640, 642-646, 648-649, 651, 654, 661, 663, 673-674, 676-678, 680, 682, 691-694, 696, 699, 704, 707-708, 710, 720-722, 726-729, 731-735, 737-738, 740, 743, 748, 750, 760-761, 763-765, 767, 769, 780, 782-783, 786-788, 791, 798, 811-813, 815, 819, 823, 826, 829-830, 832, 835-838, 840, 842-844, 846-847, 849, 857-858, 861, 863-864, 867-868, 871, 875-877, 880, 882-885, 888-894, 896-900, 902 | **B** | FastAPI: TestClient + dependency overrides. |
| `mindtrace/hardware/mindtrace/hardware/stereo_cameras/backends/basler/basler_stereo_ace.py` | 93 | 35-36, 99, 112, 172, 210, 222-223, 226, 229, 232, 235-236, 238-240, 244-246, 250, 252, 254-255, 257, 260-263, 266-267, 270, 272, 274, 280-281, 294, 341, 348-349, 352, 354-356, 361-365, 367-368, 370-371, 373, 376-377, 379-381, 384-385, 387, 397, 425-430, 449, 482-483, 500, 502-504, 515, 614, 629-630, 724, 766, 789, 810, 836, 901, 920, 969, 989, 1034, 1036-1038, 1049 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/stereo_cameras/backends/stereo_camera_backend.py` | 2 | 452-453 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/stereo_cameras/core/async_stereo_camera.py` | 37 | 59-64, 67, 70, 73-75, 78-79, 81, 130, 185, 200, 214, 236, 255, 270, 284, 298, 313, 328, 343, 358, 373, 388, 403, 421, 436, 448, 465, 484, 520, 542 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/stereo_cameras/core/models.py` | 20 | 194, 206-208, 210, 212-215, 218-220, 223-224, 227-229, 232-234 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/stereo_cameras/core/stereo_camera.py` | 26 | 56-58, 60, 62, 64-66, 68-70, 73-74, 76, 78-79, 356, 373, 390, 407, 424, 441, 458, 477, 496, 516 | **B** | Hardware (non-core-package): backends and managers; mocks/fakes. |
| `mindtrace/hardware/mindtrace/hardware/stereo_cameras/setup/__init__.py` | 2 | 12, 14 | **C** | Device/setup scripts; unit-test only extracted pure helpers. |
| `mindtrace/hardware/mindtrace/hardware/stereo_cameras/setup/setup_stereo_ace.py` | 285 | 53-61, 63-66, 68-69, 72, 80, 89-91, 94, 111, 124, 126-127, 129-130, 132-133, 136-137, 139-140, 142, 144-146, 148, 155-156, 159, 161, 167, 170, 173, 175-177, 180, 183, 186-188, 190, 193-195, 198, 200, 202, 216, 218, 220, 222-225, 227-229, 231, 233, 235, 237-242, 244, 246, 248-250, 252-255, 257, 259, 268, 270-271, 273-275, 278, 280, 282-284, 287-289, 291-292, 294, 305-306, 308-309, 312, 315-318, 320-321, 323, 332, 334-336, 338, 340-343, 345-346, 348, 357, 359-362, 364-365, 367-371, 373, 382, 384-385, 388-389, 392, 395, 397-398, 400-401, 404-411, 413-415, 417, 420-421, 424, 427-428, 431-432, 434-436, 438, 441, 444, 446-447, 449-452, 454, 456, 458, 482-483, 485-486, 488, 490-492, 495-499, 502-511, 513, 515, 517, 529, 531, 533, 547, 549, 555, 557-559, 561, 563-566, 568, 574, 576-579, 581-582, 584-586, 588, 594, 596-598, 600-602, 604-607, 609-611, 614-615, 655-656, 658-659, 664-666, 668-669, 671-672, 675-676, 698-699, 701-702, 706-708, 710-711, 713-714, 717, 719, 722-723 | **C** | Device/setup scripts; unit-test only extracted pure helpers. |
| `mindtrace/models/mindtrace/models/__init__.py` | 2 | 92-93 | **A** | Package exports; compatibility smoke tests. |
| `mindtrace/models/mindtrace/models/architectures/backbones/__init__.py` | 16 | 40-41, 51-52, 56-57, 61-62, 66-67, 71-72, 82-83, 92-93 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/architectures/backbones/adapters.py` | 8 | 32-33, 39-40, 168, 183, 265-266 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/architectures/backbones/dino.py` | 5 | 72-73, 78-79, 85 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/architectures/backbones/dino_hf.py` | 4 | 91-92, 99-100 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/architectures/backbones/efficientnet.py` | 4 | 109-110, 113-114 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/architectures/backbones/hf_generic.py` | 2 | 38-39 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/architectures/backbones/vit.py` | 4 | 93-94, 97-98 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/architectures/factory.py` | 7 | 40-42, 60-62, 310 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/archivers/__init__.py` | 8 | 15-16, 21-22, 27-28, 35-36 | **B** | SDK/filesystem; mock I/O. |
| `mindtrace/models/mindtrace/models/archivers/huggingface/hf_model_archiver.py` | 13 | 21-23, 61, 161, 200-201, 239-240, 264-265, 273-274 | **B** | SDK/filesystem; mock I/O. |
| `mindtrace/models/mindtrace/models/archivers/huggingface/hf_processor_archiver.py` | 7 | 33-35, 67, 85, 132-133 | **B** | SDK/filesystem; mock I/O. |
| `mindtrace/models/mindtrace/models/archivers/onnx/onnx_model_archiver.py` | 9 | 19-21, 56, 96, 100, 104, 129, 147 | **B** | SDK/filesystem; mock I/O. |
| `mindtrace/models/mindtrace/models/archivers/timm/timm_model_archiver.py` | 11 | 23-24, 54, 94-95, 98, 112-113, 135, 151, 193 | **B** | SDK/filesystem; mock I/O. |
| `mindtrace/models/mindtrace/models/archivers/ultralytics/__init__.py` | 2 | 11-12 | **B** | SDK/filesystem; mock I/O. |
| `mindtrace/models/mindtrace/models/archivers/ultralytics/yolo_archiver.py` | 13 | 41, 46-48, 55-56, 58-63, 65 | **B** | SDK/filesystem; mock I/O. |
| `mindtrace/models/mindtrace/models/auto_segmenter.py` | 10 | 90-94, 96, 101, 176, 186, 195 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/evaluation/metrics/detection.py` | 7 | 53, 63, 238-240, 251-252 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/serving/onnx/service.py` | 1 | 56 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/serving/service.py` | 5 | 150-151, 161-162, 321 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/serving/torchserve/client.py` | 1 | 83 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/serving/torchserve/exporter.py` | 2 | 84-85 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/serving/torchserve/handler.py` | 6 | 48, 56, 59, 62, 65, 68 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/tracking/bridges.py` | 2 | 127-128 | **B** | Case-by-case: prefer pure-function extraction where possible. |
| `mindtrace/models/mindtrace/models/training/datalake_bridge.py` | 8 | 113, 121-124, 149, 223, 227 | **B** | Training loops; tiny tensors + mocked loaders. |
| `mindtrace/models/mindtrace/models/training/trainer.py` | 4 | 200-201, 403-404 | **B** | Training loops; tiny tensors + mocked loaders. |

## Suggested unit-test priorities (by tier)

- **Tier A** — Add first when touching the area: cheap sanity checks (validation, pure helpers, `mindtrace-core`).
- **Tier B** — Worth it with mocks / `TestClient` / fakes; err on the side of a narrow regression test when behavior is easy to pin.
- **Tier C** — Usually skip in unit suite unless you split out a testable function.

### Tier A (3 files, sorted by missing count)

- `mindtrace/hardware/mindtrace/hardware/services/cameras/models/requests.py` — **18** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/plcs/models/requests.py` — **6** missing statements
- `mindtrace/models/mindtrace/models/__init__.py` — **2** missing statements

### Tier B (111 files, sorted by missing count)

- `mindtrace/hardware/mindtrace/hardware/cameras/backends/basler/basler_camera_backend.py` — **431** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/stereo_cameras/service.py` — **341** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/scanners_3d/service.py` — **304** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/cameras/service.py` — **288** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/backends/genicam/genicam_camera_backend.py` — **272** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/plcs/service.py` — **225** missing statements
- `mindtrace/hardware/mindtrace/hardware/scanners_3d/backends/photoneo/photoneo_backend.py` — **207** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/core/async_camera_manager.py` — **176** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/backends/opencv/opencv_camera_backend.py` — **131** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/core/async_camera.py` — **130** missing statements
- `mindtrace/hardware/mindtrace/hardware/core/config.py` — **125** missing statements
- `mindtrace/hardware/mindtrace/hardware/stereo_cameras/backends/basler/basler_stereo_ace.py` — **93** missing statements
- `mindtrace/cluster/mindtrace/cluster/core/cluster.py` — **82** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/backends/camera_backend.py` — **77** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/scanners_3d/connection_manager.py` — **63** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/stereo_cameras/connection_manager.py` — **62** missing statements
- `mindtrace/agents/mindtrace/agents/core/base.py` — **61** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/commands/camera.py` — **60** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/core/capture_groups.py` — **59** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/plcs/connection_manager.py` — **59** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/commands/scanner.py` — **58** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/commands/stereo.py` — **58** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/utils/display.py` — **53** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/commands/plc.py` — **52** missing statements
- `mindtrace/agents/mindtrace/agents/_function_schema.py` — **46** missing statements
- `mindtrace/hardware/mindtrace/hardware/scanners_3d/backends/scanner_3d_backend.py` — **41** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/commands/status.py` — **40** missing statements
- `mindtrace/hardware/mindtrace/hardware/scanners_3d/core/models.py` — **37** missing statements
- `mindtrace/hardware/mindtrace/hardware/stereo_cameras/core/async_stereo_camera.py` — **37** missing statements
- `mindtrace/database/mindtrace/database/backends/mongo_odm.py` — **35** missing statements
- `mindtrace/automation/mindtrace/automation/label_studio/label_studio_api.py` — **33** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/backends/basler/mock_basler_camera_backend.py` — **31** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/__main__.py` — **26** missing statements
- `mindtrace/hardware/mindtrace/hardware/stereo_cameras/core/stereo_camera.py` — **26** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/core/process_manager.py` — **24** missing statements
- `mindtrace/agents/mindtrace/agents/execution/rabbitmq.py` — **20** missing statements
- `mindtrace/hardware/mindtrace/hardware/stereo_cameras/core/models.py` — **20** missing statements
- `mindtrace/hardware/mindtrace/hardware/plcs/backends/allen_bradley/allen_bradley_plc.py` — **19** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/homography/calibrator.py` — **18** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/sensors/service.py` — **17** missing statements
- `mindtrace/hardware/mindtrace/hardware/plcs/backends/base.py` — **16** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/cameras/launcher.py` — **16** missing statements
- `mindtrace/models/mindtrace/models/architectures/backbones/__init__.py` — **16** missing statements
- `mindtrace/cluster/mindtrace/cluster/workers/environments/git_env.py` — **14** missing statements
- `mindtrace/hardware/mindtrace/hardware/plcs/backends/allen_bradley/mock_allen_bradley.py` — **14** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/plcs/launcher.py` — **13** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/scanners_3d/launcher.py` — **13** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/sensors/launcher.py` — **13** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/stereo_cameras/launcher.py` — **13** missing statements
- `mindtrace/models/mindtrace/models/archivers/huggingface/hf_model_archiver.py` — **13** missing statements
- `mindtrace/models/mindtrace/models/archivers/ultralytics/yolo_archiver.py` — **13** missing statements
- `mindtrace/agents/mindtrace/agents/models/_model.py` — **12** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/__init__.py` — **11** missing statements
- `mindtrace/hardware/mindtrace/hardware/plcs/plc_manager.py` — **11** missing statements
- `mindtrace/models/mindtrace/models/archivers/timm/timm_model_archiver.py` — **11** missing statements
- `mindtrace/models/mindtrace/models/auto_segmenter.py` — **10** missing statements
- `mindtrace/agents/mindtrace/agents/core/abstract.py` — **9** missing statements
- `mindtrace/models/mindtrace/models/archivers/onnx/onnx_model_archiver.py` — **9** missing statements
- `mindtrace/agents/mindtrace/agents/profiles/__init__.py` — **8** missing statements
- `mindtrace/models/mindtrace/models/architectures/backbones/adapters.py` — **8** missing statements
- `mindtrace/models/mindtrace/models/archivers/__init__.py` — **8** missing statements
- `mindtrace/models/mindtrace/models/training/datalake_bridge.py` — **8** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/core/camera.py` — **7** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/cameras/connection_manager.py` — **7** missing statements
- `mindtrace/models/mindtrace/models/architectures/factory.py` — **7** missing statements
- `mindtrace/models/mindtrace/models/archivers/huggingface/hf_processor_archiver.py` — **7** missing statements
- `mindtrace/models/mindtrace/models/evaluation/metrics/detection.py` — **7** missing statements
- `mindtrace/hardware/mindtrace/hardware/sensors/backends/mqtt.py` — **6** missing statements
- `mindtrace/hardware/mindtrace/hardware/services/__init__.py` — **6** missing statements
- `mindtrace/models/mindtrace/models/serving/torchserve/handler.py` — **6** missing statements
- `mindtrace/agents/mindtrace/agents/_tool_manager.py` — **5** missing statements
- `mindtrace/agents/mindtrace/agents/memory/_store.py` — **5** missing statements
- `mindtrace/agents/mindtrace/agents/providers/_provider.py` — **5** missing statements
- `mindtrace/models/mindtrace/models/architectures/backbones/dino.py` — **5** missing statements
- `mindtrace/models/mindtrace/models/serving/service.py` — **5** missing statements
- `mindtrace/agents/mindtrace/agents/execution/_queue.py` — **4** missing statements
- `mindtrace/datalake/mindtrace/datalake/service.py` — **4** missing statements
- `mindtrace/hardware/mindtrace/hardware/sensors/simulators/base.py` — **4** missing statements
- `mindtrace/models/mindtrace/models/architectures/backbones/dino_hf.py` — **4** missing statements
- `mindtrace/models/mindtrace/models/architectures/backbones/efficientnet.py` — **4** missing statements
- `mindtrace/models/mindtrace/models/architectures/backbones/vit.py` — **4** missing statements
- `mindtrace/models/mindtrace/models/training/trainer.py` — **4** missing statements
- `mindtrace/agents/mindtrace/agents/history/__init__.py` — **3** missing statements
- `mindtrace/agents/mindtrace/agents/models/openai_chat.py` — **3** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/backends/basler/__init__.py` — **3** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/backends/opencv/__init__.py` — **3** missing statements
- `mindtrace/hardware/mindtrace/hardware/cli/core/logger.py` — **3** missing statements
- `mindtrace/agents/mindtrace/agents/execution/local.py` — **2** missing statements
- `mindtrace/agents/mindtrace/agents/providers/gemini.py` — **2** missing statements
- `mindtrace/agents/mindtrace/agents/providers/ollama.py` — **2** missing statements
- `mindtrace/agents/mindtrace/agents/providers/openai.py` — **2** missing statements
- `mindtrace/agents/mindtrace/agents/toolsets/_toolset.py` — **2** missing statements
- `mindtrace/agents/mindtrace/agents/toolsets/mcp.py` — **2** missing statements
- `mindtrace/datalake/mindtrace/datalake/sync.py` — **2** missing statements
- `mindtrace/hardware/mindtrace/hardware/__init__.py` — **2** missing statements
- `mindtrace/hardware/mindtrace/hardware/plcs/backends/__init__.py` — **2** missing statements
- `mindtrace/hardware/mindtrace/hardware/scanners_3d/core/scanner_3d.py` — **2** missing statements
- `mindtrace/hardware/mindtrace/hardware/sensors/core/manager.py` — **2** missing statements
- `mindtrace/hardware/mindtrace/hardware/sensors/simulators/mqtt.py` — **2** missing statements
- `mindtrace/hardware/mindtrace/hardware/stereo_cameras/backends/stereo_camera_backend.py` — **2** missing statements
- `mindtrace/models/mindtrace/models/architectures/backbones/hf_generic.py` — **2** missing statements
- `mindtrace/models/mindtrace/models/archivers/ultralytics/__init__.py` — **2** missing statements
- `mindtrace/models/mindtrace/models/serving/torchserve/exporter.py` — **2** missing statements
- `mindtrace/models/mindtrace/models/tracking/bridges.py` — **2** missing statements
- `mindtrace/agents/mindtrace/agents/core/wrapper.py` — **1** missing statements
- `mindtrace/agents/mindtrace/agents/memory/toolset.py` — **1** missing statements
- `mindtrace/agents/mindtrace/agents/prompts.py` — **1** missing statements
- `mindtrace/automation/mindtrace/automation/workers/pipeline_worker.py` — **1** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/homography/measurer.py` — **1** missing statements
- `mindtrace/models/mindtrace/models/serving/onnx/service.py` — **1** missing statements
- `mindtrace/models/mindtrace/models/serving/torchserve/client.py` — **1** missing statements

### Tier C (7 files, sorted by missing count)

- `mindtrace/hardware/mindtrace/hardware/scanners_3d/setup/setup_photoneo.py` — **540** missing statements
- `mindtrace/hardware/mindtrace/hardware/stereo_cameras/setup/setup_stereo_ace.py` — **285** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/setup/setup_basler.py` — **40** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/setup/setup_genicam.py` — **38** missing statements
- `mindtrace/hardware/mindtrace/hardware/cameras/setup/setup_cameras.py` — **11** missing statements
- `mindtrace/hardware/mindtrace/hardware/scanners_3d/setup/__init__.py` — **2** missing statements
- `mindtrace/hardware/mindtrace/hardware/stereo_cameras/setup/__init__.py` — **2** missing statements

## Notes

- **Exhaustive** means every file with any miss is listed; long range strings are intact (not truncated).
- Optional `ImportError` / `pragma: no cover` environments may still appear as misses; only add tests if CI supports that configuration.
