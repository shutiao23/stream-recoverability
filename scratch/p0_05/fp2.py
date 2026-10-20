import os
D = '/home/lzq/workspace/parttime/stream-recoverability/results/wrr_submission_ready/major_revision_20261014/p0_05_power_and_independence/'
names = sorted(os.listdir(D))
for n in names:
    print(repr(n), os.path.exists(D + n))
