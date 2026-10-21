# Split QA

**Verdict: FAIL** (CVE component crossing)

Manifest v0.2 · seed 42 · dataset_hash `9c3442a78ade`

## Checks

| check | violations | status | meaning |
| --- | --- | --- | --- |
| manifest row counts | 0 | PASS | rows per split equal the manifest |
| (project, commit) group crossing | 0 | PASS | one (project, commit) group in >1 split |
| commit crossing | 0 | PASS | one commit hash in >1 split |
| project crossing | 0 | PASS | one project in >1 split |
| CVE component crossing | 164 | FAIL | CVEs linked by a shared row or commit appear in >1 split |
| exact code-hash overlap | 0 | PASS | identical code in >1 split |
| whitespace-insensitive overlap | 1 | WARN | same code ignoring whitespace in >1 split |
| CVE ids in >1 split | 364 | WARN | single CVE id seen in more than one split (information) |

## Per split

| split | rows | share | target | label_1 | label_0 | projects | commit_groups | cves | largest_group_share | largest_project_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train | 339328 | 0.7246 | 0.7 | 21155 | 318173 | 420 | 7779 | 7125 | 0.0137 | 0.2902 |
| val | 42995 | 0.0918 | 0.1 | 2701 | 40294 | 378 | 1401 | 1428 | 0.0206 | 0.1302 |
| test | 42996 | 0.0918 | 0.1 | 2710 | 40286 | 362 | 1169 | 1170 | 0.0445 | 0.0445 |
| holdout | 42996 | 0.0918 | 0.1 | 2711 | 40285 | 338 | 1264 | 1193 | 0.0307 | 0.1346 |

## Per CWE (vulnerable rows, top 40 of 198)

| cwe | rows | rows_train | rows_val | rows_test | rows_holdout | projects | commit_groups | cves | largest_group_share | largest_project_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CWE-119 | 45123 | 32181.0 | 5058.0 | 3975.0 | 3909.0 | 241 | 1461 | 1558 | 0.0144 | 0.2453 |
| CWE-20 | 36358 | 27599.0 | 3080.0 | 2255.0 | 3424.0 | 176 | 1039 | 1177 | 0.0283 | 0.3105 |
| CWE-416 | 33529 | 25846.0 | 2661.0 | 2147.0 | 2875.0 | 125 | 774 | 873 | 0.0451 | 0.4152 |
| CWE-787 | 31609 | 19944.0 | 3854.0 | 3106.0 | 4705.0 | 281 | 1035 | 1166 | 0.0418 | 0.1425 |
| CWE-476 | 30912 | 20217.0 | 3972.0 | 3178.0 | 3545.0 | 177 | 895 | 1021 | 0.0435 | 0.2626 |
| CWE-125 | 29785 | 17205.0 | 3280.0 | 4862.0 | 4438.0 | 235 | 1159 | 1268 | 0.0332 | 0.0787 |
| CWE-399 | 22131 | 19853.0 | 993.0 | 554.0 | 731.0 | 50 | 516 | 561 | 0.0661 | 0.481 |
| CWE-264 | 18905 | 15947.0 | 1578.0 | 162.0 | 1218.0 | 65 | 424 | 508 | 0.0546 | 0.4266 |
| CWE-200 | 17906 | 13775.0 | 1263.0 | 1635.0 | 1233.0 | 98 | 513 | 586 | 0.021 | 0.3798 |
| CWE-190 | 14977 | 9158.0 | 2251.0 | 1381.0 | 2187.0 | 162 | 503 | 589 | 0.066 | 0.1423 |
| CWE-362 | 14855 | 12395.0 | 842.0 | 769.0 | 849.0 | 50 | 346 | 404 | 0.0312 | 0.5577 |
| CWE-401 | 11904 | 9931.0 | 620.0 | 629.0 | 724.0 | 65 | 226 | 262 | 0.391 | 0.4183 |
| CWE-189 | 10601 | 7619.0 | 1228.0 | 1208.0 | 546.0 | 70 | 316 | 363 | 0.0571 | 0.3471 |
| CWE-400 | 7489 | 4864.0 | 1370.0 | 167.0 | 1088.0 | 61 | 192 | 214 | 0.0885 | 0.4014 |
| CWE-120 | 7445 | 4565.0 | 506.0 | 1077.0 | 1297.0 | 121 | 255 | 275 | 0.0399 | 0.1049 |
| CWE-415 | 6763 | 3041.0 | 715.0 | 2457.0 | 550.0 | 65 | 140 | 175 | 0.2826 | 0.2826 |
| CWE-835 | 5869 | 4335.0 | 662.0 | 415.0 | 457.0 | 59 | 200 | 227 | 0.0767 | 0.2646 |
| CWE-254 | 5613 | 4516.0 | 89.0 | 633.0 | 375.0 | 20 | 94 | 108 | 0.1315 | 0.7002 |
| CWE-617 | 4986 | 2382.0 | 590.0 | 1910.0 | 104.0 | 46 | 156 | 182 | 0.1258 | 0.1919 |
| CWE-22 | 4549 | 2812.0 | 1045.0 | 554.0 | 138.0 | 94 | 136 | 144 | 0.1622 | 0.1622 |
| CWE-834 | 4333 | 3917.0 | 330.0 | 29.0 | 57.0 | 12 | 49 | 57 | 0.7757 | 0.8795 |
| CWE-772 | 3881 | 2624.0 | 680.0 | 382.0 | 195.0 | 32 | 193 | 213 | 0.0734 | 0.2136 |
| CWE-284 | 3381 | 2672.0 | 273.0 | 336.0 | 100.0 | 32 | 95 | 107 | 0.1778 | 0.3511 |
| CWE-369 | 3221 | 1777.0 | 688.0 | 670.0 | 86.0 | 50 | 162 | 188 | 0.055 | 0.1273 |
| CWE-404 | 2744 | 1331.0 | 181.0 | 924.0 | 308.0 | 19 | 41 | 54 | 0.2828 | 0.356 |
| CWE-59 | 2503 | 1708.0 | 414.0 | 293.0 | 88.0 | 37 | 64 | 66 | 0.2449 | 0.2449 |
| CWE-74 | 2468 | 1798.0 | 191.0 | 319.0 | 160.0 | 28 | 42 | 38 | 0.1921 | 0.3035 |
| CWE-732 | 2177 | 1806.0 | 159.0 | 191.0 | 21.0 | 20 | 34 | 37 | 0.2384 | 0.6174 |
| CWE-122 | 2174 | 2054.0 | 77.0 | 10.0 | 33.0 | 13 | 85 | 94 | 0.0777 | 0.8565 |
| CWE-770 | 2145 | 1209.0 | 390.0 | 35.0 | 511.0 | 44 | 89 | 99 | 0.1534 | 0.1534 |
| CWE-310 | 2110 | 1673.0 | 88.0 | 187.0 | 162.0 | 21 | 67 | 81 | 0.1237 | 0.2521 |
| CWE-674 | 2094 | 1442.0 | 108.0 | 189.0 | 355.0 | 33 | 64 | 78 | 0.1175 | 0.3095 |
| CWE-287 | 2080 | 1635.0 | 130.0 | 131.0 | 184.0 | 52 | 75 | 70 | 0.1053 | 0.2346 |
| CWE-295 | 2079 | 995.0 | 212.0 | 338.0 | 534.0 | 34 | 51 | 50 | 0.1198 | 0.1972 |
| CWE-269 | 1940 | 1463.0 | 218.0 | 79.0 | 180.0 | 33 | 65 | 58 | 0.1325 | 0.2711 |
| CWE-89 | 1850 | 1477.0 | 230.0 | 31.0 | 112.0 | 24 | 39 | 41 | 0.2773 | 0.7449 |
| CWE-908 | 1840 | 1362.0 | 102.0 | 41.0 | 335.0 | 35 | 69 | 96 | 0.0875 | 0.2299 |
| CWE-79 | 1833 | 1493.0 | 148.0 | 32.0 | 160.0 | 72 | 118 | 129 | 0.108 | 0.4883 |
| CWE-19 | 1732 | 1567.0 | 11.0 | 145.0 | 9.0 | 13 | 36 | 42 | 0.2523 | 0.515 |
| CWE-134 | 1677 | 1247.0 | 93.0 | 184.0 | 153.0 | 21 | 23 | 27 | 0.3524 | 0.3524 |

## Examples: CVE component crossing

| cve_component | splits | rows | cves | projects |
| --- | --- | --- | --- | --- |
| CVE-2011-2802 | test, train, val | 22498 | CVE-2011-2802, CVE-2011-2835, CVE-2011-3046, CVE-2011-3084 | android, chromium/chromium, ffmpeg/ffmpeg, skia |
| CVE-2007-1592 | holdout, test, train, val | 22199 | CVE-2007-1592, CVE-2007-2480, CVE-2007-4567, CVE-2008-1514 | android, kernel/git/bluetooth/bluetooth, kernel/git/bluetooth/bluetooth-next, kernel/git/bpf/bpf-next |
| CVE-2010-3698 | holdout, train | 6280 | CVE-2010-3698, CVE-2010-3881, CVE-2010-5313, CVE-2012-1601 | kernel/git/avi/kvm, torvalds/linux, xen-project/xen |
| CVE-2005-4881 | holdout, train, val | 3012 | CVE-2005-4881, CVE-2009-3612, CVE-2011-2525, CVE-2012-6536 | flar2/elementalx-n9, kernel/git/netdev/net, torvalds/linux |
| CVE-2009-0746 | holdout, train | 2780 | CVE-2009-0746, CVE-2009-0747, CVE-2009-0748, CVE-2009-2849 | kernel/git/tytso/ext4, torvalds/linux |
| CVE-2011-4566 | holdout, train | 1853 | CVE-2011-4566, CVE-2013-7226, CVE-2014-2020, CVE-2014-5386 | facebook/hhvm, libgd/libgd, php/php-src |
| CVE-2016-4817 | holdout, train, val | 1519 | CVE-2016-4817, CVE-2018-6343, CVE-2019-15226, CVE-2021-43825 | alibaba/tengine, apache/trafficserver, envoyproxy/envoy, facebook/proxygen |
| CVE-2017-7185 | holdout, test, train | 1489 | CVE-2017-7185, CVE-2018-12684, CVE-2019-12951, CVE-2019-13503 | ceph/civetweb, cesanta/mongoose, cesanta/mongoose-os, civetweb/civetweb |
| CVE-2016-2383 | train, val | 1440 | CVE-2016-2383, CVE-2016-4557, CVE-2016-4558, CVE-2017-16995 | kernel/git/bpf/bpf, kernel/git/netdev/net, kernel/git/tip/tip, torvalds/linux |
| CVE-2014-9907 | train, val | 1266 | CVE-2014-9907, CVE-2015-8895, CVE-2015-8896, CVE-2015-8900 | imagemagick/imagemagick, imagemagick/imagemagick6 |

## Examples: whitespace-insensitive overlap

| hash | splits | rows |
| --- | --- | --- |
| 35a4619feebf1469b28fdf0f4b2618b7046a033fc8577f7e0bab24ed8aedbc7c | test, train | 2 |
