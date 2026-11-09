# r4��ֻ�޸� Full / Clip ��·���������

��һ��ֻ��һ����ѡ��**r3 + clip-vg �� PackedGraph ·�����������޸�**���������� r3 Ⱦɫ�建�棬ֻ����ִ��������Ӱ��� `clip-vg` ���ԭ `04.join.sh`��vg��GFAffix���ü�������·������˳�򱣳ֲ��䡣

## �޸�����֤��Χ

`PackedPath` �Ĳ���/��������ӵ�д����ڴ棻��ײ� SDSL �ƶ�����û�� `noexcept`��`std::vector::reserve()` ������ܸ�����������·�����顣Full ɾ�� minigraph Ƭ�Ρ�Clip �ж�·��ʱ��������·��������������ݡ������ȷ����µ��������������ʽ�ƶ���������Ȩ������·��˳��·������벽��ƫ�ơ�ֻ�޸� clip-vg ʹ�õ� STL backend��Mapped backend ���ġ�

�� r3 �� chr21 Full / Clip ��ֵ�ֱ�Լ 418.3 / 419.4 GiB��**����Ŀ���������ֱ𲻳��� 300 GiB����ͼ������֤ȫ�� PASS��300 GiB ������Ŀ�꣬�����Ѿ���õ� chr21 �����**

ʹ��ͬһ�̶� jemalloc `54eaed1d8b56b1aa528be3bdd1877e59c56fa90c` �ı��� 60,000 �ڵ��ֲ��ԣ�

| ���� | r3 RSS��KiB�� | r4 RSS��KiB�� | �ڴ潵�� | r3 / r4 ��ʱ |
|---|---:|---:|---:|---:|
| Full | 267,416 | 180,884 | 32.4% | 1.02 / 0.83 �� |
| Clip | 308,328 | 197,816 | 35.8% | 25.83 / 26.26 �� |

Full �� 60,001 ������ڵ㡢323 ��·���� Clip �� 60,000 ������ڵ㡢641 ��·����ͨ����ڵ�/��/����·������Ƚϡ��úϳɲ���֧�ָ�������ݵȼ��ԣ������� chr21 �������ͬ�����ĸ��ƣ�������Ҫ�����ڴ棬����ŵ Clip ���١�

��������׶���֤����ȫ���ڵ� ID/���С�˫���ڽӡ�·������/Ԫ����/���α�Ǻ���������������衣����ð��һ���µ�ȫ���� 37 �ļ���֤��r3 �� 37/37 ���н������������

## 1. �� A ��������

������ r3 ��ͬ�� GCC/Cactus ���������ֽ����� clip-vg ���� libbdsg�������±������� vg����Ҫ A ��ԭ�е� r2/r3 ����Ŀ¼��ʹ����Ŀ¼�������ɰ�װ��

```bash
SOFT="$HOME/softwares"
SRC="$SOFT/vg-join-candidate-r4"
R2="$SOFT/cactus-join-candidate-r2"
R3="$SOFT/cactus-join-candidate-r3"
R4="$SOFT/cactus-join-candidate-r4"

git clone --no-checkout https://github.com/yeeus/vg.git "$SRC"
# �˴�ʹ�ñ��ֻظ��ṩ�������̶� commit��
git -C "$SRC" checkout --detach <R4_COMMIT>
bash "$SRC/benchmarks/cactus_join/upgrade_r4.sh" "$R3" "$R2" "$R4" 8
```

ͨ����׼��`PASS r4 clip-vg build and exact graph checks`�����������¾�������ʵ clip-vg ���� Full/Clip������ 1/4 �߳�ִ��ͬһ�ϸ�ͼ��֤��������־�� `$R4/build.clip.candidate.log`��

������ԭ���� A��B ���䷽ʽ���� `$R4/candidate/`��`$R4/source.commit`��`$R4/reused_r3.prefix` �ͱ��� `$SRC` �� benchmark �ű����� B ��ӦĿ¼��B ����Ҫ����Դ���װ�µ�ͼ������

## 2. �� B ������ chr21 �������

�� chr21 Ŀ¼������ Slurm ������Դ�����С����һ�ֱ��� r3 ��ͬ�������Դ�ͽڵ����ͣ��Ȳ���ʵ RSS���پ�������Ⱦɫ����������ڴ档

```bash
SRC="$HOME/softwares/vg-join-candidate-r4"
PREFIX="$HOME/softwares/cactus-join-candidate-r4"
CACHE="$PWD/join_bench_r3/candidate/stage_cache"
WORK="$PWD/join_bench_r4"

python3 -u "$SRC/benchmarks/cactus_join/clip_stages.py" run \
    --stage full --cache "$CACHE" --prefix "$PREFIX" --out "$WORK"

python3 -u "$SRC/benchmarks/cactus_join/clip_stages.py" run \
    --stage clip --cache "$CACHE" --prefix "$PREFIX" --out "$WORK"
```

��������˳�����У�Ҳ�ɷֱ��������������Դ���õ���ҵ���ű��Զ���黺�����뱣���С���ܾ�����ͬ������Ŀ¼��

Full ��ʵ���������� `27e9f0581e2fa662ae912b1b/04-clip-0.json`��

```bash
clip-vg 03-unchop-0.gfaffixed -f -e GRCh38 -d _MINIGRAPH_ -L -F
```

Clip �Ȱ� `27e9f0581e2fa662ae912b1b/04-clip-1.clip` ���Ƶ���Ŀ¼���Ը���ִ��ԭ `join_vg()` �е� `vg ids -j`�������� `d5a62368ba95a450c7748df9/04-clip-0.json` �����

```bash
vg ids -j clip.input.vg
clip-vg clip.input.vg -f -e GRCh38 -d _MINIGRAPH_ \
    -u 10000 -a _MINIGRAPH_ -I 100000 -k 50000 -T -1.0
```

��������������� r3 ���� `04-clip-0.stage0`�������� control ��ҵ��Clip ʹ�þ� r3 Full ��������Ը�����һ�βü����ڴ�仯���� Full ����������֤��� Full ��ȫ��ͬ�������ں� vg �����ʵ��û�б仯�����β��ظ�ִ�С�

����������Լ 410 GiB��Full ���Լ 192 GiB��Clip ���븱��Լ 192 GiB��Clip ���Լ 23 GiB����������������ԭ r3 ���治�ᱻ��д��Ҳ��ʹ��Ӳ���ӡ�

ÿ���׶ε������ `$WORK/full/`��`$WORK/clip/`��

- `result.vg`���½����
- `time.log`��GNU time �� wall/CPU/Maximum resident set size���� Linux RSS ��λ�� KiB��
- `cpu_memory.tsv`��`process_cpu_memory.tsv`��ÿ 5 �������
- `run.log`������ `clip_phase=` ����־�����з�ֵ�ǽ����ý׶ε��ۼ����ֵ��
- `summary.json`���˳�״̬����Դ���ܡ�
- `command.json`��ʵ����������Ƚϵ� r3 �ļ���

Clip �ĸ���/���ͬ���������� `prepare.log`��`prepare.time.log`�������� clip-vg �����ĺ�ʱ���ֵ��

## 3. ���߳� verify

�������ɹ��������㹻�ڴ�ļ�����Դ��ִ�У�

```bash
python3 -u "$SRC/benchmarks/cactus_join/clip_stages.py" verify \
    --prefix "$PREFIX" --out "$WORK" --threads 16 \
    > "$WORK/verify.log" 2>&1
```

ͨ����׼��`PASS full`��`PASS clip`���� `$WORK/verify/report.json` �� `pass` Ϊ `true`��ÿ��ͼ�ı���/ɢ��ʹ�� 16 �̣߳����غ���֤����ͼ��˳��ִ�У������ڴ���ӡ�����Ƚ�ͼ���ݣ����� PackedGraph ������/���л����ֱ仯��

��ش����� `time.log`������ `summary.json` �� `verify/report.json`����Щ�����жϴ˴��ڴ��Ƿ��꣬�����ϴ����� GiB ��ͼ��

## 4. ͨ������������Ⱦɫ��

����ʹ��ԭ���� `04.join.sh`��ֻ������ runtime �������Ŀ¼��

```bash
python3 "$SRC/benchmarks/cactus_join/run.py" candidate "$PREFIX" \
    "$PWD/join_bench_r4/candidate" "$PWD/04.join.sh"
```

��������µ�ȫ���̽��������Ҫ�� chr21 �� r3 37 �������ļ��ٴ�������գ����������ʹ������ͳһ��֤����

```bash
python3 -u "$SRC/benchmarks/cactus_join/verify.py" \
    "$PWD/join_bench_r3/candidate" "$PWD/join_bench_r4/candidate" \
    --vg "$PREFIX/candidate/bin/vg" --threads 16 \
    --tmp "$PWD/join_bench_r4" --output "$PWD/join_bench_r4/verify_all"
```

���׶��ڴ�����������ϸ�ͼ��֤�󣬲���Ϊ���ڴ����ظ����� chr21 join�����������Ƚ�����������ȫ���̺�����õ���֤��Χ��
