# Cactus 7f34bb7��ԭ����һ�����ڴ��ѡ

**���һ�� Full/Clip �ڴ��޸����� [r4 �������롢�����������߳���֤](BENCHMARK_R4.md)��ֻ����һ����ѡ��**

**�������ʹ��[ͳһ��ʽ��֤��](VERIFY_ALL_FORMATS.md)�����°� verify.py �Ѻϲ� GBZ��ODGI �� TBI �ĸ��顣**

**���˲����� make_xg ����requesting 4.0 cores��ʱ���� [�����޸������� jobStore ����](SINGLE_CORE_XG_FIX.md)��**

**��һ�� control �� candidate �Ĺ��������к���֤�� [r3 ��׼����](BENCHMARK_R3.md)��**

**GFA/XG PASS��VCF �ȶ��� FAIL���� [���ڲ�������� VCF ר���](VERIFY_DATE_DIFFERENCES.md)��** ֻ������ȷ�ϵ��������ڣ���������������������¼�������ʧ�ܡ�

**���� candidate ����ʷ chr21 `final/` �Ƚϣ��� [��ʷ�����֤](VERIFY_HISTORICAL.md)��** �°� `verify.py --legacy-control` ����û�� benchmark Ԫ���ݵľ� final������ȷ��¼�����ľɰ�����ļ����������������鼰���̷߳�ʽ������

**candidate �� `vg deconstruct` / VCF header �� SIGSEGV���ұ���� `-DNDEBUG`���� [VCF ��ʼ���޸������� jobStore ����](VCF_HEADER_FIX.md)��** ����Դ���� A ʱֻ���� A �������룬�ٰ� vg �����ƴ��� B������������ɵ� full/clip��

**r1 chr21 OOM ���밴 [r2 �ָ�˵��](RECOVERY_R2.md) �������������ܡ�** r2 �������� vg/GFAffix���޸� clip-vg �� jemalloc ����������������ͼ������־ý׶λ��棻���汣�� r1 ����ƺ���֤��Χ���ο����� r1 ������������ڻָ���

ֻ���� `control` �� `candidate`���������� V1�CV7��ԭ `04.join.sh` ���ģ�ÿ��ʹ�ö��� jobStore��workDir��final ����־Ŀ¼���������ο���filter=132 ��ԭ������ϡ�

## 1. ���ء�����

�ȼ���ԭ���� Cactus/GCC ������ȷ�� `vg version` Ϊ `v1.76.1-89-gf2ed0bbd4`����Ҫ GCC��10��C++20��ԭ vg �Ĺ���������Meson��1.3��Rust/Cargo��1.85��Python��psutil��verify���� GNU sort��h5diff������˵���� [vg README](../../README.md#compiling-vg)��

```bash
SOFT=/path/to/softwares
SRC="$SOFT/vg-join-candidate-r1"
PREFIX="$SOFT/cactus-join-candidate-r1"
ORIGINAL_VG="$SOFT/cactus-master-7f34bb7/bin/vg"

git clone --filter=blob:none --branch cactus-7f34bb7-lowmem https://github.com/yeeus/vg.git "$SRC"
cd "$SRC"
# ����������˹̶��ύ���ڴ�ִ�� git checkout --detach <���ύ>��
bash benchmarks/cactus_join/build.sh "$PREFIX" "$ORIGINAL_VG" 16
```

`SRC`��`PREFIX` ��ʹ����Ŀ¼���ű�����һ����ѡ��control �� vg ʹ��ԭ�����ƺ͵���������ԭ�� libhandlegraph��gfaffix/clip-vg ����ͬһ���뻷���ֱ𹹽�ԭ�����ѡ������ʧ�ܻ�ֹͣ��ͨ��Сͼ�������� `Build and small differential checks passed`��ȫ��������־�������汾��Դ���ύ������ PREFIX��

����ѡ������GFA ����ʱ���ο�������gfaffix ��ʽ����/·���ͽ���ԭͼУ�飻�ں� GFA ������ unchop���ں� full ���ĶΡ�clip �����Ρ�filter ���Σ�vg �� clip-vg ���Ե�·����Ա����ԭ����������·�����4�̸߳��±�ţ�ֱ�Ӱ�λ������ XG ���������� gfaffix transformation check��vg validate��vg ids -j��HAL��ODGI ��ͳ�Ʋ��衣

## 2. ������������ join

���������ͬһ�� **chr21 Ŀ¼**ִ�У���Ŀ¼����ԭ `cactus.config.sh`��`align/chr21.vg`��HAL �� SV-GFA��`SCRIPT` ָ��ԭʼ04�ű��������������**��Դ��ͬ���ֱ������Դ�ļ�����ҵ**�У����ֱ���֮ǰ64��/500GԤ�㣬����Դ�������ǰ�����ڴ档

```bash
SRC=/path/to/softwares/vg-join-candidate-r1
PREFIX=/path/to/softwares/cactus-join-candidate-r1
SCRIPT=/path/to/original/04.join.sh
WORK="$PWD/join_bench_r1"

# ��ҵһ
python3 "$SRC/benchmarks/cactus_join/run.py" control "$PREFIX" "$WORK/control" "$SCRIPT"

# ��ҵ����������ҵ���Դ�ͬһ��chr21Ŀ¼����
python3 "$SRC/benchmarks/cactus_join/run.py" candidate "$PREFIX" "$WORK/candidate" "$SCRIPT"
```

������� Slurm �ṩ������ `SLURM_CPUS_PER_TASK` �� `SLURM_MEM_PER_NODE`�����ֹ�α����Դ���䡣��˳���ύ�����⹲���ڵ㾺���������ܱȽϡ�ʧ�ܺ��������ļ������Զ����ǻ����ܡ�

�ű��ڼ���ԭ���ú��л���Ӧ����/�⣬��ѡͨ��˽�� `PYTHONPATH` ���� join ģ�飬���Ĺ��� Cactus����ѧ����ԭ��������ֻ��������Ŀ¼�������� Toil `retryCount=0` / `stopOnFirstFailure=True`����Ŀ�����ü���ʹ��ԭʼ������������äĿ�����ںϡ�

ÿ����Ҫ����

- `logs/04.join.log`��ʵ��������׶κ�ʱ������`logs/04.join.time.log`��GNU time��
- `cpu_memory.tsv`��`process_cpu_memory.tsv`��`summary.json`��ÿ5����/�����CPU��RSS��ȫ�̻��ܡ�
- `tools.log`��`inputs.log`��`run.join.sh`��ʵ�ʹ���/��̬�⡢�������ú�����ִ�нű���

## 3. ���߳� verify

����ɹ��˳������������֤��ҵ���߳�ʾ��Ϊ8���ڴ����ֱ������Լ���ԭͼ��Ԥ�㣬��֤��һ��ֻ����һ��ͼ��

```bash
VERIFY_THREADS=8
/usr/bin/time -v -o "$WORK/verify.time.log" \
python3 "$SRC/benchmarks/cactus_join/verify.py" \
    "$WORK/control" "$WORK/candidate" \
    --vg "$PREFIX/candidate/bin/vg" \
    --threads "$VERIFY_THREADS" --tmp "$WORK" --output "$WORK/verify"
```

ͨ����׼���˳���0��`verify/report.json` �� `pass` Ϊ `true`����ÿ�������ļ���ΪPASS���˶��������£�

| �ļ� | ��� | ���з�ʽ |
|---|---|---|
| VG | �ڵ�ID/���С�����˫���ڽӡ�·��Ԫ���ݺ�ȫ������step | ͼ�ڽڵ�/�߷ֿ顢·�����̣߳�ͼ������� |
| XG | ����ͼ���ݣ��Լ����������ֽ� | ͼ�ڶ��̣߳������ֽڼ������ |
| GFA/GFA.gz | ȫ����¼���ֶΣ������Լ�¼֮������˳�򣬱���P/W�ڲ�step˳�� | GNU sort���̣߳�512MiB���򻺳壬�ⲿ�������� |
| VCF/VCF.gz | ����ͷ����ȫ����¼�������������ͺ���λ��������fileDate��bcftools����ĩβ���ڣ���������������汾 | ���ļ�������ʽ�Ƚ� |
| HAL | ȫ��HDF5���ݼ������ԣ�������������/����ʱ��� | h5diff����������ͨ�ļ���鲢�� |
| GBZ��ODGI��haplo����������/ͳ���ļ� | ȫ�ļ��ֽڣ�gzip�ļ��ȽϽ�ѹ��ȫ���� | ���ļ����У�ÿ������4MiB |

ͼָ������Ϊv3������ֱ�Ӻ;�v1/v2ָ�ƱȽϣ�verify����ͬһ������֤���������顣����ͼ������ڵ㡢���̶�ȡ���д��в��֣�`--threads 8`������ÿһ�붼ʹ��8�ˡ�

GFA�ⲿ����ʹ�ô��̻��ڴ棻��ʱ����������������ѹGFA��sort��д�ļ���`--tmp`�ɸ�Ϊ����ڵ�Ĵ�����scratch��

GBZ/haplo�ȶ���������Ϸ��洢˳��ͬ���ֽڲ�һ�£�Ҳ�ᱣ�ص�FAIL�������ļ������һ���˶ԣ����������˻��ɡ�·��������ͬ����ͨ������ֻ��ȫ�����ͨ�������ܳƱ��ν������һ�¡�

## 4. �Ƚ���Դ

`verify/report.json` �������� `workflow_resources`���Ƚ�ǽ��Сʱ��CPU��Сʱ��`cpu_seconds/3600`������󵥽���RSS�Ͳ���������RSS��������Ϳ����ظ����㹲��ҳ��5���������©��˲ʱ��ֵ��GNU time�������ļ�ϵͳ����/���������

���Ǻ�ѡ�汾����Ԥ�ȳ�ŵchr21���ٱ�����chr1/chr2�ڴ����ޡ�����Ⱦɫ�����ܼ�ȫ������һ���ԣ����������鼯Ⱥ���Ϊ׼��

���������Linux���߱��롢32��GFAffix���ա�40��·����Ա������9000�ڵ㲢��ָ�Ƽ�顢��������ͼ������������ԭ��/��ѡ���գ���ʵ��GBZ��XG�ͽ���verify����˽��Cactus����ƴ����ԭ�ű������Ѽ�飻����Slurm/ToilȾɫ����ҵ��δ�ڱ���ִ�С�
