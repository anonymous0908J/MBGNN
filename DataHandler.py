import pickle
import numpy as np
from scipy.sparse import csr_matrix
from Params import args
import scipy.sparse as sp
from Utils.TimeLogger import log

def transpose(mat):
	coomat = sp.coo_matrix(mat)
	return csr_matrix(coomat.transpose())

def negSamp(temLabel, sampSize, nodeNum):
	negset = [None] * sampSize
	cur = 0
	while cur < sampSize:
		rdmItm = np.random.choice(nodeNum)
		if temLabel[rdmItm] == 0:
			negset[cur] = rdmItm
			cur += 1
	return negset

def transToLsts(mat, mask=False, norm=False):
	shape = [mat.shape[0], mat.shape[1]]
	coomat = sp.coo_matrix(mat)
	indices = np.array(list(map(list, zip(coomat.row, coomat.col))), dtype=np.int32)
	data = coomat.data.astype(np.float32)

	if norm:
		rowD = np.squeeze(np.array(1 / (np.sqrt(np.sum(mat, axis=1) + 1e-8) + 1e-8)))
		colD = np.squeeze(np.array(1 / (np.sqrt(np.sum(mat, axis=0) + 1e-8) + 1e-8)))
		for i in range(len(data)):
			row = indices[i, 0]
			col = indices[i, 1]
			data[i] = data[i] * rowD[row] * colD[col]

	# half mask
	if mask:
		spMask = (np.random.uniform(size=data.shape) > 0.5) * 1.0
		data = data * spMask

	if indices.shape[0] == 0:
		indices = np.array([[0, 0]], dtype=np.int32)
		data = np.array([0.0], np.float32)
	return indices, data, shape

def loadPretrnEmbeds():
	with open('pretrain/PreTrnEmbed_usr', 'rb') as fs:
		usrEmbeds = pickle.load(fs)
	with open('pretrain/PreTrnEmbed_itm', 'rb') as fs:
		itmEmbeds = pickle.load(fs)
	return np.array(usrEmbeds), np.array(itmEmbeds)

class DataHandler:
	def __init__(self):
		if args.data == 'yelp':
			predir = 'Datasets/Yelp/%s/seq/' % args.target
			behs = ['tip', 'neg', 'neutral', 'pos']
		elif args.data == 'ml10m':
			predir = 'Datasets/MultiInt-ML10M/%s/seq/' % args.target
			behs = ['neg', 'neutral', 'pos']
		elif args.data == 'tmall':
			predir = 'Datasets/Tmall/%s/' % args.target
			behs = ['pv', 'fav', 'cart', 'buy']
			# behs = ['buy']
		elif args.data == 'beibei':
			predir = 'Datasets/beibei/%s/' % args.target
			behs = ['pv', 'cart', 'buy']
		elif args.data == 'tianchi':
			predir = 'Datasets/Tianchi/%s/' % args.target
			behs = ['click', 'fav', 'cart', 'buy']
			# behs = ['click', 'cart', 'buy']

		if args.behAb == 0:
			behs = behs
		elif args.behAb == 1:
			behs = behs[1:]
		elif args.behAb == 2:
			behs = behs[:1] + behs[2:]
		elif args.behAb == 3:
			if len(behs) > 3:
				behs = behs[:2] + behs[3:]
			elif len(behs) == 3:
				behs = behs[2:]
		elif args.behAb == 4:
			behs = behs[-1:]
		else:
			print('ERROR')
		print(behs)

		self.predir = predir
		self.behs = behs
		self.trnfile = predir + 'trn_'
		self.tstfile = predir + 'tst_'

	def LoadData(self, trans=False):
		trnMats = list()
		for i in range(len(self.behs)):
			beh = self.behs[i]
			path = self.trnfile + beh
			with open(path, 'rb') as fs:
				mat = (pickle.load(fs) != 0).astype(np.float32)
			trnMats.append(mat)
			if args.target == 'click':
				trnLabel = (mat if i==0 else 1 * (trnLabel + mat != 0))
			elif args.target == 'buy' and i == len(self.behs) - 1:
				trnLabel = 1 * (mat != 0)
		# test set
		path = self.tstfile + 'int'
		with open(path, 'rb') as fs:
			tstInt = np.array(pickle.load(fs))

		if trans:
			for i in range(len(self.behs)):
				trnMats[i] = transpose(trnMats[i])
			trnLabel = transpose(trnLabel)
			temTstInt = [None] * trnLabel.shape[0]
			for i in range(trnLabel.shape[1]):
				if tstInt[i] != None:
					temu = i
					temi = tstInt[i]
					temTstInt[temi] = temu
			tstInt = np.array(temTstInt)

		tstStat = (tstInt != None)
		tstUsrs = np.reshape(np.argwhere(tstStat != False), [-1])

		self.trnMats = trnMats
		self.trnLabel = trnLabel
		self.tstInt = tstInt
		self.tstUsrs = tstUsrs
		args.user, args.item = self.trnMats[0].shape
		args.behNum = len(self.behs)
		self.prepareGlobalData()

	def prepareGlobalData(self):
		adj = 0
		for i in range(args.behNum):
			adj = adj + self.trnMats[i]
		adj = (adj != 0).astype(np.float32)
		self.labelP = np.squeeze(np.array(np.sum(adj, axis=0)))
		tpadj = transpose(adj)
		adjNorm = np.reshape(np.array(np.sum(adj, axis=1)), [-1])
		tpadjNorm = np.reshape(np.array(np.sum(tpadj, axis=1)), [-1])
		for i in range(adj.shape[0]):
			for j in range(adj.indptr[i], adj.indptr[i+1]):
				adj.data[j] /= adjNorm[i]
		for i in range(tpadj.shape[0]):
			for j in range(tpadj.indptr[i], tpadj.indptr[i+1]):
				tpadj.data[j] /= tpadjNorm[i]
		self.adj = adj
		self.tpadj = tpadj

	def sampleLargeGraph(self, pckUsrs, pckItms=None, sampDepth=2, sampNum=args.graphSampleN, preSamp=False):
		adj = self.adj
		tpadj = self.tpadj
		def makeMask(nodes, size):
			mask = np.ones(size)
			if not nodes is None:
				mask[nodes] = 0.0
			return mask

		def updateBdgt(adj, nodes):
			if nodes is None:
				return 0
			tembat = 1000
			ret = 0
			for i in range(int(np.ceil(len(nodes) / tembat))):
				st = tembat * i
				ed = min((i+1) * tembat, len(nodes))
				temNodes = nodes[st: ed]
				ret += np.sum(adj[temNodes], axis=0)
			return ret

		def sample(budget, mask, sampNum):
			score = (mask * np.reshape(np.array(budget), [-1])) ** 2
			norm = np.sum(score)
			if norm == 0:
				return np.random.choice(len(score), 1), sampNum - 1
			score = list(score / norm)
			arrScore = np.array(score)
			posNum = np.sum(np.array(score)!=0)
			if posNum < sampNum:
				pckNodes1 = np.squeeze(np.argwhere(arrScore!=0))
				# pckNodes2 = np.random.choice(np.squeeze(np.argwhere(arrScore==0.0)), min(len(score) - posNum, sampNum - posNum), replace=False)
				# pckNodes = np.concatenate([pckNodes1, pckNodes2], axis=0)
				pckNodes = pckNodes1
			else:
				pckNodes = np.random.choice(len(score), sampNum, p=score, replace=False)
			return pckNodes, max(sampNum - posNum, 0)

		def constructData(usrs, itms):
			adjs = self.trnMats
			pckAdjs = []
			pckTpAdjs = []
			for i in range(len(adjs)):
				pckU = adjs[i][usrs]
				tpPckI = transpose(pckU)[itms]
				pckTpAdjs.append(tpPckI)
				pckAdjs.append(transpose(tpPckI))
			return pckAdjs, pckTpAdjs, usrs, itms

		usrMask = makeMask(pckUsrs, adj.shape[0])
		itmMask = makeMask(pckItms, adj.shape[1])
		itmBdgt = updateBdgt(adj, pckUsrs)
		if pckItms is None:
			pckItms, _ = sample(itmBdgt, itmMask, len(pckUsrs))
			itmMask = itmMask * makeMask(pckItms, adj.shape[1])
		usrBdgt = updateBdgt(tpadj, pckItms)
		uSampRes = 0
		iSampRes = 0
		for i in range(sampDepth + 1):
			uSamp = uSampRes + (sampNum if i < sampDepth else 0)
			iSamp = iSampRes + (sampNum if i < sampDepth else 0)
			newUsrs, uSampRes = sample(usrBdgt, usrMask, uSamp)
			usrMask = usrMask * makeMask(newUsrs, adj.shape[0])
			newItms, iSampRes = sample(itmBdgt, itmMask, iSamp)
			itmMask = itmMask * makeMask(newItms, adj.shape[1])
			if i == sampDepth or i == sampDepth and uSampRes == 0 and iSampRes == 0:
				break
			usrBdgt += updateBdgt(tpadj, newItms)
			itmBdgt += updateBdgt(adj, newUsrs)
		usrs = np.reshape(np.argwhere(usrMask==0), [-1])
		itms = np.reshape(np.argwhere(itmMask==0), [-1])
		return constructData(usrs, itms)
