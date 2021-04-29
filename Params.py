import argparse

def parse_args():
	parser = argparse.ArgumentParser(description='Model Params')
	parser.add_argument('--lr', default=2e-4, type=float, help='learning rate')
	parser.add_argument('--batch', default=32, type=int, help='batch size')
	parser.add_argument('--reg', default=5e-2, type=float, help='weight decay regularizer')
	parser.add_argument('--epoch', default=120, type=int, help='number of epochs')
	parser.add_argument('--decay', default=0.99, type=float, help='weight decay rate')
	parser.add_argument('--save_path', default='tem', help='file name to save model and training record')
	parser.add_argument('--latdim', default=16, type=int, help='embedding size')
	parser.add_argument('--mult', default=1e2, type=float, help='mult for pred')
	parser.add_argument('--memosize', default=8, type=int, help='memory size')
	parser.add_argument('--sampNum', default=40, type=int, help='batch size for sampling')
	parser.add_argument('--attHead', default=2, type=int, help='number of attention heads')
	parser.add_argument('--trnNum', default=10000, type=int, help='number of training instances per epoch')
	parser.add_argument('--load_model', default=None, help='model name to load')
	parser.add_argument('--shoot', default=10, type=int, help='K of top k')
	parser.add_argument('--data', default='beibei', type=str, help='name of dataset')
	parser.add_argument('--target', default='buy', type=str, help='target behavior to predict on')
	parser.add_argument('--gnn_layer', default=2, type=int, help='number of gnn layers')
	parser.add_argument('--save_embed', default=False, type=bool, help='whether to save learned embeddings for pretraining code')
	parser.add_argument('--preTrn_item', default=False, type=bool, help='Pretrain for user embeddings or item embeddings')
	parser.add_argument('--test_epoch', default=3, type=int, help='how many epoches to test')
	parser.add_argument('--tstEpoch', default=3, type=int, help='number of epoch to test while training')
	parser.add_argument('--divSize', default=10000, type=int, help='div size for smallTestEpoch')
	parser.add_argument('--graphSampleN', default=20000, type=int, help='use 25000 for training and 200000 for testing, empirically')
	parser.add_argument('--keepRate', default=1.0, type=float, help='keep rate for edge dropout')
	parser.add_argument('--behAb', default=0, type=int, help='indicator for behavior ablation')
	return parser.parse_args()
args = parse_args()
# tianchi
# args.user = 423423
# args.item = 874328
# beibei
# args.user = 21716
# args.item = 7977
# Tmall
# args.user = 805506#147894
# args.item = 584050#99037
# ML10M
# args.user = 67788
# args.item = 8704
# yelp
# args.user = 19800
# args.item = 22734

args.decay_step = args.trnNum // args.batch
