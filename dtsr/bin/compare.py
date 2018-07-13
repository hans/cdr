import sys
import argparse
import numpy as np
import pandas as pd
from dtsr.config import Config
from dtsr.signif import bootstrap
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

if __name__ == '__main__':

    argparser = argparse.ArgumentParser('''
        Computes pairwise significance of error differences between DTSR models and competitors.
    ''')
    argparser.add_argument('config_path', help='Path to configuration (*.ini) file')
    argparser.add_argument('-m', '--models', nargs='*', default=[], help='Path to configuration (*.ini) file')
    argparser.add_argument('-a', '--ablation', action='store_true', help='Only compare models within an ablation set (those defined using the "ablate" param in the config file)')
    argparser.add_argument('-p', '--partition', type=str, default='dev', help='Name of partition to use (one of "train", "dev", "test")')
    argparser.add_argument('-M', '--metric', type=str, default='loss', help='Metric to use for comparison (either "loss" or "loglik")')
    argparser.add_argument('-t', '--tails', type=int, default=2, help='Number of tails (1 or 2)')
    args, unknown = argparser.parse_known_args()

    p = Config(args.config_path)
    if len(args.models) > 0:
        models = args.models
    else:
        models = p.model_list[:]

    sys.stderr.write('\n')
    dtsr_models = [x for x in models if x.startswith('DTSR')]

    if args.ablation:
        comparison_sets = {}
        for model_name in dtsr_models:
            model_basename = model_name.split('!')[0]
            if model_basename not in comparison_sets:
                comparison_sets[model_basename] = []
            comparison_sets[model_basename].append(model_name)
    else:
        comparison_sets = {
            None: dtsr_models
        }

    for s in comparison_sets:
        model_set = comparison_sets[s]
        if len(model_set) > 1:
            if s is not None:
                sys.stderr.write('Comparing models within ablation set "%s"...\n' %s)
            for i in range(len(model_set)):
                m1 = model_set[i]
                p.set_model(m1)

                if args.metric == 'loss':
                    file_name = '/%s_losses_%s.txt' % (p['loss_name'], args.partition)
                else:
                    file_name = '/loglik_%s.txt' % args.partition

                for j in range(i+1, len(model_set)):
                    m2 = model_set[j]
                    name = '%s_v_%s' %(m1, m2)
                    a = pd.read_csv(p.outdir + '/' + m1 + file_name, sep=' ', header=None, skipinitialspace=True)
                    b = pd.read_csv(p.outdir + '/' + m2 + file_name, sep=' ', header=None, skipinitialspace=True)
                    select = np.logical_and(np.isfinite(np.array(a)), np.isfinite(np.array(b)))
                    diff = float(len(a) - select.sum())
                    p_value, base_diff, diffs = bootstrap(a[select], b[select], n_iter=10000, n_tails=args.tails, mode=args.metric)
                    sys.stderr.write('\n')
                    with open(p.outdir + '/' + name + '_ptsignif_' + args.partition + '.txt', 'w') as f:
                        f.write('='*50 + '\n')
                        f.write('Model comparison: %s vs %s\n' %(m1, m2))
                        if diff > 0:
                            f.write('%d NaN rows filtered out (out of %d)\n' %(diff, len(a)))
                        f.write('Partition: %s\n' %args.partition)
                        f.write('Loss difference: %.4f\n' %base_diff)
                        f.write('p: %.4e%s\n' %(p_value, '' if p_value > 0.05 else '*' if p_value > 0.01 else '**' if p_value > 0.001 else '***'))
                        f.write('='*50 + '\n')
                    plt.hist(diffs, bins=1000)
                    plt.savefig(p.outdir + '/' + name + '_' + args.partition + '.png')
                    plt.close('all')
