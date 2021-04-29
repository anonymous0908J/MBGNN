import numpy as np
from Params import args
import Utils.TimeLogger as logger
from Utils.TimeLogger import log
import Utils.NNLayers as NNs
from Utils.NNLayers import FC, Regularize, Activate, Dropout, Bias, getParam, defineParam
from DataHandler import negSamp, transpose, DataHandler, transToLsts
import tensorflow as tf
from tensorflow.core.protobuf import config_pb2
import pickle
import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

class Recommender:
	def __init__(self, sess, handler):
		self.sess = sess
		self.handler = handler

		# # sparsity test
		# trnMat = np.sum(self.handler.trnMats)
		# trnnum = np.reshape(np.array(np.sum(trnMat, axis=1)), [-1])
		# chsn = (trnnum <= 707) * (trnnum > 234)
		# newTstUsrs = list()
		# for usr in self.handler.tstUsrs:
		# 	if chsn[usr]:
		# 		newTstUsrs.append(usr)
		# self.handler.tstUsrs = np.array(newTstUsrs)
		# print(len(newTstUsrs), 'usrs chosen')

		print('USER', args.user, 'ITEM', args.item)
		self.metrics = dict()
		mets = ['Loss', 'preLoss', 'HR', 'NDCG']
		for met in mets:
			self.metrics['Train'+met] = list()
			self.metrics['Test'+met] = list()

	def makePrint(self, name, ep, reses, save):
		ret = 'Epoch %d/%d, %s: ' % (ep, args.epoch, name)
		for metric in reses:
			val = reses[metric]
			ret += '%s = %.4f, ' % (metric, val)
			tem = name + metric
			if save and tem in self.metrics:
				self.metrics[tem].append(val)
		ret = ret[:-2] + '  '
		return ret

	def run(self):
		self.prepareModel()
		log('Model Prepared')
		if args.load_model != None:
			self.loadModel()
			stloc = len(self.metrics['TrainLoss']) * args.tstEpoch - (args.tstEpoch - 1)
		else:
			stloc = 0
			init = tf.global_variables_initializer()
			self.sess.run(init)
			log('Variables Inited')
		for ep in range(stloc, args.epoch):
			test = (ep % args.test_epoch == 0)
			reses = self.trainEpoch()
			log(self.makePrint('Train', ep, reses, test))
			if test:
				reses = self.testEpoch()
				log(self.makePrint('Test', ep, reses, test))
				self.saveHistory()
			print()
		reses = self.testEpoch()
		log(self.makePrint('Test', args.epoch, reses, True))
		self.saveHistory()

	def transMsg(self, feature, multMats):
		catlat1 = []
		paramId = 'dfltP%d' % NNs.getParamId()
		for inp in multMats:
			temlat = tf.sparse.sparse_dense_matmul(inp, feature)
			# memo att for context learning
			memoatt = FC(tf.identity(temlat), args.memosize, activation='relu', reg=True, useBias=True)
			memoTrans = tf.reshape(FC(memoatt, args.latdim**2, reg=True, name=paramId, reuse=True), [-1, args.latdim, args.latdim])
			transLat = tf.reduce_sum(tf.reshape(temlat, [-1, args.latdim, 1]) * memoTrans, axis=1)
			# transLat = FC(temlat, args.latdim, reg=True, useBias=True)
			catlat1.append(transLat)
			self.translats.append(transLat)
		# catlat2 = catlat1
		catlat2 = NNs.selfAttention(catlat1, number=args.behNum, inpDim=args.latdim, numHeads=args.attHead)
		# aggregation gate
		weights = []
		paramId = 'dfltP%d' % NNs.getParamId()
		for catlat in catlat2:
			temlat = FC(catlat, args.latdim//2, useBias=True, reg=True, activation='relu', name=paramId+'_1', reuse=True)
			weight = FC(temlat, 1, useBias=True, reg=True, name=paramId+'_2', reuse=True)
			weights.append(weight)
		stkWeight = tf.concat(weights, axis=1)
		sftWeight = tf.reshape(tf.nn.softmax(stkWeight, axis=1), [-1, args.behNum, 1])
		stkCatlat = tf.stack(catlat2, axis=1)
		lat = tf.squeeze(tf.reduce_sum(sftWeight * stkCatlat, axis=1))
		# lat = tf.reshape(tf.reduce_mean(stkCatlat, axis=1), [-1, args.latdim])
		for i in range(0):
			lat = FC(lat, args.latdim, reg=True, useBias=True, activation='relu') + lat
		return lat

	def edgeDropout(self, mats):
		def dropOneMat(mat):
			indices = mat.indices
			values = mat.values
			shape = mat.dense_shape
			# newVals = tf.to_float(tf.sign(tf.nn.dropout(values, self.keepRate)))
			newVals = tf.nn.dropout(values, self.keepRate)
			return tf.sparse.SparseTensor(indices, newVals, shape)
		ret = []
		for mat in mats:
			ret.append(dropOneMat(mat))
		return ret

	def ours(self):
		self.translats = list()
		UEmbed = NNs.defineParam('UEmbed', shape=[args.user, args.latdim], dtype=tf.float32, reg=True)
		IEmbed = NNs.defineParam('IEmbed', shape=[args.item, args.latdim], dtype=tf.float32, reg=True)
		ulats = [UEmbed]
		ilats = [IEmbed]
		for i in range(args.gnn_layer):
			ulat = self.transMsg(ilats[-1], self.edgeDropout(self.uiMats))
			ilat = self.transMsg(ulats[-1], self.edgeDropout(self.iuMats))
			# ulat = self.transMsg(ilats[-1], self.uiMats)
			# ilat = self.transMsg(ulats[-1], self.iuMats)
			ulats.append(ulat)
			ilats.append(ilat)

		for i in range(args.gnn_layer+1):
			ulats[i] = ulats[i] / (1e-6+tf.sqrt(1e-6+tf.reduce_sum(tf.square(ulats[i]), axis=-1, keepdims=True)))
			ilats[i] = ilats[i] / (1e-6+tf.sqrt(1e-6+tf.reduce_sum(tf.square(ilats[i]), axis=-1, keepdims=True)))

		ulats[0] = NNs.defineParam('UEmbedPred', shape=[args.user, args.latdim], dtype=tf.float32, reg=False)
		ilats[0] = NNs.defineParam('IEmbedPred', shape=[args.item, args.latdim], dtype=tf.float32, reg=False)

		# # ablation on attentive multi-order pred
		# ulat = FC(tf.concat(ulats, axis=1), args.latdim, reg=True, useBias=True, name='ablation_trans', activation='relu')
		# ilat = FC(tf.concat(ilats, axis=1), args.latdim, reg=True, useBias=True, name='ablation_trans', reuse=True, activation='relu')
		# pckUlat = tf.nn.embedding_lookup(ulat, self.uids)
		# pckIlat = tf.nn.embedding_lookup(ilat, self.iids)
		# predLat = pckUlat * pckIlat

		latnum = len(ulats)
		ulats = tf.stack(ulats, axis=1)
		ilats = tf.stack(ilats, axis=1)

		pckULats = tf.reshape(tf.nn.embedding_lookup(ulats, self.uids), [-1, args.latdim])
		pckILats = tf.reshape(tf.nn.embedding_lookup(ilats, self.iids), [-1, args.latdim])
		ukeys = tf.reshape(FC(pckULats, args.latdim, reg=True, name='key', reuse=True), [-1, latnum, 1, args.attHead, args.latdim//args.attHead])
		ikeys = tf.reshape(FC(pckILats, args.latdim, reg=True, name='key', reuse=True), [-1, 1, latnum, args.attHead, args.latdim//args.attHead])
		uvals = tf.reshape(FC(pckULats, args.latdim, reg=True, name='val', reuse=True), [-1, latnum, 1, args.attHead, args.latdim//args.attHead])
		ivals = tf.reshape(FC(pckILats, args.latdim, reg=True, name='val', reuse=True), [-1, 1, latnum, args.attHead, args.latdim//args.attHead])
		# uvals = tf.reshape(pckULats, [-1, latnum, 1, args.attHead, args.latdim//args.attHead])
		# ivals = tf.reshape(pckILats, [-1, 1, latnum, args.attHead, args.latdim//args.attHead])

		att = Activate(tf.reduce_sum(ukeys * ikeys, axis=-1, keepdims=True), 'relu')
		# att = tf.reshape(tf.nn.softmax(tf.reshape(tf.reduce_sum(ukeys * ikeys, axis=-1), [-1, (latnum)**2, args.attHead]), axis=1), [-1, latnum, latnum, args.attHead, 1])
		self.att = tf.squeeze(att)

		lat = uvals * ivals
		predLat = tf.reshape(tf.reduce_sum(att * lat, axis=[1, 2]), [-1, args.latdim]) * args.mult


		for i in range(1):
			predLat = FC(predLat, args.latdim, reg=True, useBias=True, activation='relu') + predLat
		pred = tf.squeeze(FC(predLat, 1, reg=True, useBias=True))# * args.mult

		return pred

	def prepareModel(self):
		self.keepRate = tf.placeholder(dtype=tf.float32, shape=[])
		self.uiMats = []
		self.iuMats = []
		for i in range(args.behNum):
			idx, data, shape = transToLsts(self.handler.trnMats[i])
			self.uiMats.append(tf.sparse.SparseTensor(idx, data, shape))
			tpmat = transpose(self.handler.trnMats[i])
			idx, data, shape = transToLsts(tpmat)
			self.iuMats.append(tf.sparse.SparseTensor(idx, data, shape))
		self.uids = tf.placeholder(dtype=tf.int32, shape=[None])
		self.iids = tf.placeholder(dtype=tf.int32, shape=[None])

		self.pred = self.ours()
		sampNum = tf.shape(self.iids)[0]//2
		posPred = tf.slice(self.pred, [0], [sampNum])
		negPred = tf.slice(self.pred, [sampNum], [-1])
		self.preLoss = tf.reduce_sum(tf.maximum(0.0, 1.0 - (posPred - negPred))) / args.batch
		self.regLoss = args.reg * Regularize()
		self.loss = self.preLoss + self.regLoss

		globalStep = tf.Variable(0, trainable=False)
		learningRate = tf.train.exponential_decay(args.lr, globalStep, args.decay_step, args.decay, staircase=True)
		self.optimizer = tf.train.AdamOptimizer(learningRate).minimize(self.loss, global_step=globalStep)

	def sampleTrainBatch(self, batchIds):
		temLabel = self.handler.trnLabel[batchIds].toarray()
		batch = len(batchIds)
		temlen = batch * 2 * args.sampNum
		uIntLoc = [None] * temlen
		iIntLoc = [None] * temlen
		cur = 0
		for i in range(batch):
			posset = np.reshape(np.argwhere(temLabel[i]!=0), [-1])
			poslocs = np.random.choice(posset, args.sampNum)
			neglocs = negSamp(temLabel[i], args.sampNum, args.item)
			for j in range(args.sampNum):
				posloc = poslocs[j]
				negloc = neglocs[j]
				uIntLoc[cur] = uIntLoc[cur+temlen//2] = batchIds[i]
				iIntLoc[cur] = posloc
				iIntLoc[cur+temlen//2] = negloc
				cur += 1
		return uIntLoc, iIntLoc

	def trainEpoch(self):
		num = args.user
		sfIds = np.random.permutation(num)[:args.trnNum]
		epochLoss, epochPreLoss = [0] * 2
		num = len(sfIds)
		steps = int(np.ceil(num / args.batch))

		for i in range(steps):
			st = i * args.batch
			ed = min((i+1) * args.batch, num)
			batchIds = sfIds[st: ed]

			uIntLoc, iIntLoc = self.sampleTrainBatch(batchIds)
			target = [self.optimizer, self.preLoss, self.regLoss, self.loss]
			res = self.sess.run(target, feed_dict={self.uids: uIntLoc, self.iids: iIntLoc, self.keepRate: args.keepRate}, options=config_pb2.RunOptions(report_tensor_allocations_upon_oom=True))
			preLoss, regLoss, loss = res[1:]

			epochLoss += loss
			epochPreLoss += preLoss
			log('Step %d/%d: loss = %.2f, regLoss = %.2f          ' % (i, steps, loss, regLoss), save=False, oneline=True)
		ret = dict()
		ret['Loss'] = epochLoss / steps
		ret['preLoss'] = epochPreLoss / steps
		return ret

	def sampleTestBatch(self, batchIds):
		batch = len(batchIds)
		temTst = self.handler.tstInt[batchIds]
		temLabel = self.handler.trnLabel[batchIds].toarray()
		temlen = (batch*100)
		uIntLoc = [None] * temlen
		iIntLoc = [None] * temlen
		tstLocs = [None] * (batch)
		cur = 0
		for i in range(batch):
			posloc = temTst[i]
			negset = np.reshape(np.argwhere(temLabel[i]==0), [-1])
			rdnNegSet = np.random.permutation(negset)[:99]
			locset = np.concatenate((rdnNegSet, np.array([posloc])))
			tstLocs[i] = locset
			for j in range(100):
				uIntLoc[cur] = batchIds[i]
				iIntLoc[cur] = locset[j]
				cur += 1
		return uIntLoc, iIntLoc, temTst, tstLocs

	def testEpoch(self):
		self.atts = [None] * args.user
		epochHit, epochNdcg = [0] * 2
		ids = self.handler.tstUsrs
		num = len(ids)
		testbatch = args.batch#np.maximum(1, args.batch * args.sampNum // 100)
		steps = int(np.ceil(num / testbatch))
		for i in range(steps):
			st = i * testbatch
			ed = min((i+1) * testbatch, num)
			batchIds = ids[st: ed]
			uIntLoc, iIntLoc, temTst, tstLocs = self.sampleTestBatch(batchIds)
			preds = self.sess.run(self.pred, feed_dict={self.uids: uIntLoc, self.iids: iIntLoc, self.keepRate: 1.0}, options=config_pb2.RunOptions(report_tensor_allocations_upon_oom=True))
			hit, ndcg = self.calcRes(np.reshape(preds, [ed-st, 100]), temTst, tstLocs)
			epochHit += hit
			epochNdcg += ndcg
			log('Step %d/%d: hit = %d, ndcg = %d          ' % (i, steps, hit, ndcg), save=False, oneline=True)
		ret = dict()
		ret['HR'] = epochHit / num
		ret['NDCG'] = epochNdcg / num
		return ret

	def calcRes(self, preds, temTst, tstLocs):
		hit = 0
		ndcg = 0
		for j in range(preds.shape[0]):
			predvals = list(zip(preds[j], tstLocs[j]))
			predvals.sort(key=lambda x: x[0], reverse=True)
			shoot = list(map(lambda x: x[1], predvals[:args.shoot]))
			if temTst[j] in shoot:
				hit += 1
				ndcg += np.reciprocal(np.log2(shoot.index(temTst[j])+2))
		return hit, ndcg

	def saveHistory(self):
		if args.epoch == 0:
			return
		with open('History/' + args.save_path + '.his', 'wb') as fs:
			pickle.dump(self.metrics, fs)

		saver = tf.train.Saver()
		saver.save(self.sess, 'Models/' + args.save_path)
		log('Model Saved: %s' % args.save_path)

	def loadModel(self):
		saver = tf.train.Saver()
		saver.restore(sess, 'Models/' + args.load_model)
		with open('History/' + args.load_model + '.his', 'rb') as fs:
		    self.metrics = pickle.load(fs)
		log('Model Loaded')

if __name__ == '__main__':
	logger.saveDefault = True
	config = tf.ConfigProto()
	config.gpu_options.allow_growth = True

	log('Start')
	handler = DataHandler()
	handler.LoadData()
	log('Load Data')

	with tf.Session(config=config) as sess:
		recom = Recommender(sess, handler)
		recom.run()