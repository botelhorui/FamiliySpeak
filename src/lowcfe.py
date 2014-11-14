import math
import array


PITCH_MIN = 40
PITCH_MAX = 120
PITCH_DIF = PITCH_MAX - PITCH_MIN
POVERLAPMAX = PITCH_MAX >> 2
HISTORYLEN = (PITCH_MAX * 3 + POVERLAPMAX)
NDEC = 2
CORRLEN = 160
CORRBUFLEN = CORRLEN + PITCH_MAX
CORRMINPOWER = 250
EOVERLAPINCR = 32
FRAMESZ = 80
ATTENFAC = 0.2
ATTENINCR = ATTENFAC/FRAMESZ



def clamp_short(t):
	if t > 32767:
		t = 32767
	elif t < -32768:
		t = -32768
	return t

def overlap_add(l,li,r,ri,o,oi,cnt):
	incr = 1/cnt
	lw = 1 - incr
	rw = incr
	for i in range(cnt):			
		t = lw*l[li+i] + rw*r[ri+i]
		t = clamp_short(t)
		o[oi+i]=t
		lw-=incr
		rw+=incr

def convertfs(f,fi,t,ti,cnt):
	"""
	f = from list
	fi = f start index
	...
	"""
	for i in range(cnt):
		t[ti+i]=int(f[fi+i])




class LowcFE:
	'G711 Appendice I'
	'Low complexity Frame Erasure Concealment'

	#


	def __init__(self):
		# consecutive erased frames
		self.erasecnt = 0 
		# overlap based on pitch	
		self.poverlap = 0 	
		# offset into pitch period
		self.poffset = 0 	
		# pitch estimate
		self.pitch = 0
		# current pitch buffer length 		
		self.pitchblen = 0 	
		# index of end of pitch buffer
		self.pitchbufend = HISTORYLEN	
		# index of start of pitch buffer
		self.pitchbufstart = 0 	
		# buffer for cycles of speec
		self.pitchbuf = [0.0]*HISTORYLEN
		# saved last quarted wavelength
		self.lastq = [0.0]*POVERLAPMAX
		# history buffer
		self.history = [0]*HISTORYLEN

	def dofe(self):
		'G711'
		out = [0]*FRAMESZ 
		if self.erasecnt == 0:
			# get history
			for i in range(HISTORYLEN):
				self.pitchbuf[i]=self.history[i]

			self.pitch = self.find_pitch()
			# OLA 1/4 length
			self.poverlap = self.pitch >> 2
			# save original last poverlap samples
			self.lastq[:self.poverlap] = self.pitchbuf[-self.poverlap:]

			self.poffset=0 # 
			self.pitchblen=self.pitch
			self.pitchbufstart=self.pitchbufend-self.pitchblen

			l = self.lastq
			li = 0
			r = self.pitchbuf
			ri = self.pitchbufstart-self.poverlap
			o = self.pitchbuf
			oi = self.pitchbufend-self.poverlap
			overlap_add(l,li,r,ri,o,oi,self.poverlap)
			# update last 1/4 wavelengt in history buffer
			f = self.pitchbuf
			fi = self.pitchbufend - self.poverlap
			t = self.history
			ti = HISTORYLEN - self.poverlap
			convertfs(f,fi,t,ti,self.poverlap)
			self.getfespeech(out,FRAMESZ)

		elif self.erasecnt == 1 or self.erasecnt == 2:
			# Tail to previous pitch estimate
			tmp = [0]*POVERLAPMAX
			saveoffset = self.poffset
			self.getfespeech(tmp,self.poverlap)
			# Add period to the pitch buffer
			self.poffset=saveoffset
			while self.poffset > self.pitch:
				self.poffset -= self.pitch
			self.pitchblen += self.pitch
			self.pitchbufstart = self.pitchbufend - self.pitchblen

			l = self.lastq
			li = 0
			r = self.pitchbuf
			ri = self.pitchbufstart-self.poverlap
			o = self.pitchbuf
			oi = self.pitchbufend-self.poverlap
			overlap_add(l,li,r,ri,o,oi,self.poverlap)
			# overlap add old pitchbuffer with new
			self.getfespeech(out,FRAMESZ)

			overlap_add(tmp,0,out,0,out,0,self.poverlap)
			self.scalespeech(out)

		elif self.erasecnt > 5:
			pass #leave out filled with zeros
			self.erasecnt = 6
		else:
			self.getfespeech(out,FRAMESZ)
			self.scalespeech(out)

		self.erasecnt+=1
		out = self.save_speech(out)
		assert len(out) == FRAMESZ
		assert len(self.history) == HISTORYLEN
		return tobytes(out)

	def scalespeech(self, out):
		g = 1 - (self.erasecnt - 1) * ATTENFAC
		for i in range(FRAMESZ):
			out[i] = int(out[i]*g)
			g -= ATTENINCR



	def getfespeech(self,out,sz):
		"fills out with repeating pitch, updating poffset"
		'out is a list to be modified'
		'sz is'
		outi = 0
		while sz > 0:
			cnt = self.pitchblen-self.poffset
			if cnt > sz:
				cnt = sz
			f = self.pitchbuf
			fi = self.pitchbufstart+self.poffset
			convertfs(f,fi,out,outi,cnt)
			self.poffset += cnt

			if self.poffset == self.pitchblen:
				self.poffset=0
			outi += cnt
			sz -= cnt

	def find_pitch(self):
		# COARSE search
		pb = self.pitchbuf		
		li = self.pitchbufend - CORRLEN
		ri = self.pitchbufend - CORRBUFLEN
		energy = 0
		corr = 0
		for i in range(0,CORRLEN,NDEC):
			energy += pb[ri+i] * pb[ri+i]
			corr += pb[ri+i] * pb[li+i]
		scale = energy
		if scale < CORRMINPOWER:
			scale = CORRMINPOWER
		corr = corr / math.sqrt(scale)
		bestcorr = corr
		bestmatch = 0
		for j in range(NDEC,PITCH_DIF+1,NDEC):
			energy -= pb[ri + 0] * pb[ri + 0]
			energy += pb[ri + CORRLEN] * pb[ri + CORRLEN]
			ri += NDEC
			corr = 0
			for i in range(0,CORRLEN,NDEC):
				corr += pb[ri + i] * pb[li + i]
			scale = energy
			if scale < CORRMINPOWER:
				scale = CORRMINPOWER
			corr /= math.sqrt(scale)
			if corr > bestcorr:
				bestcorr = corr
				bestmatch = j
		# FINE SEARCH
		j = bestmatch - (NDEC - 1)
		if j < 0:
			j = 0
		k = bestmatch + (NDEC - 1)
		if k > PITCH_DIF:
			k = PITCH_DIF
		ri = self.pitchbufend - CORRBUFLEN + j
		energy = 0
		corr = 0
		for i in range(CORRLEN):
			energy += pb[ri+i] * pb[ri+i]
			corr += pb[ri+i] * pb[li + i]
		scale = energy
		if scale < CORRMINPOWER:
			scale = CORRMINPOWER
		corr = corr / math.sqrt(scale)
		bestcorr = corr
		bestmatch = j
		for j in range(j+1,k+1):			
			energy -= pb[ri + 0] * pb[ri + 0]
			energy += pb[ri + CORRLEN] * pb[ri + CORRLEN]
			ri += 1
			corr = 0
			for i in range(0,CORRLEN):
				corr += pb[ri + i] * pb[li + i]
			scale = energy
			if scale < CORRMINPOWER:
				scale = CORRMINPOWER
			corr /= math.sqrt(scale)
			if corr > bestcorr:
				bestcorr = corr
				bestmatch = j

		return PITCH_MAX - bestmatch
	
	def add_to_history(self,data):
		'G711'
		'data is bytes'			
		s = array.array("h",data).tolist()
		assert len(s) == FRAMESZ
		if self.erasecnt:
			overlapbuf = [0]*FRAMESZ
			olen = self.poverlap + (self.erasecnt - 1) * EOVERLAPINCR
			if olen > FRAMESZ:
				olen=FRAMESZ
			self.getfespeech(overlapbuf,olen)
			self.overlap_add_at_end(s,overlapbuf,olen) #TODO see pdf again
			self.erasecnt=0
		s = self.save_speech(s)		
		return tobytes(s)

	def save_speech(self,s):
		's is list of shorts'
		assert len(s) == FRAMESZ
		h = self.history		
		h[:-FRAMESZ]=h[FRAMESZ:]
		h[-FRAMESZ:]=s
		return h[-FRAMESZ - POVERLAPMAX : -POVERLAPMAX]

	def overlap_add_at_end(self,s,f,cnt):
		""" Overlap add the end of the erasure with start of the first good frame
			Scale the syntatic speech by the gain factor before the OLA.
		"""
		incr = 1/cnt
		gain = 1 - (self.erasecnt - 1) * ATTENFAC
		if gain < 0:
			gain = 0
		incrg = incr * gain
		lw = (1-incr)*gain
		rw = incr
		for i in range(cnt):
			t = lw * f[i] + rw * s[i]
			t = int(clamp_short(t))
			s[i]=t
			lw -= incrg
			rw += incr


import unittest

def tobytes(lst):
	try:
		return array.array("h",lst).tobytes()
	except TypeError:
		print(lst)
		raise


class TestFunctions(unittest.TestCase):

	def test_save_speech(self):
		fec = LowcFE()
		s = [1]*FRAMESZ
		exp = [0]*(HISTORYLEN-FRAMESZ)+s
		out = fec.save_speech(s)
		self.assertEqual(fec.history, exp)
		exp = [0]*POVERLAPMAX + [1]*(FRAMESZ-POVERLAPMAX)
		self.assertEqual(out,exp)


	def test_add_to_history(self):
		#first frame
		fec = LowcFE()

		sb = tobytes([1]*FRAMESZ)
		out = fec.add_to_history(sb)
		x = [0]*POVERLAPMAX + [1]*(FRAMESZ-POVERLAPMAX)
		exp = tobytes(x)		
		self.assertEqual(out,exp)

		sb = tobytes([0]*FRAMESZ)
		out = fec.add_to_history(sb)
		x = [1]*POVERLAPMAX + [0]*(FRAMESZ-POVERLAPMAX)
		exp = tobytes(x)
		self.assertEqual(out,exp)

	def test_find_pitch(self):
		fec = LowcFE()
		s = [0]*HISTORYLEN
		self.assertEqual(fec.find_pitch(),PITCH_MAX)
		fec.pitchbuf[-CORRBUFLEN]=1
		fec.pitchbuf[-CORRLEN]=1
		self.assertEqual(fec.find_pitch(),PITCH_MAX)

		fec.pitchbuf=s.copy()
		fec.pitchbuf[-CORRBUFLEN+NDEC]=1
		fec.pitchbuf[-CORRLEN]=1
		self.assertEqual(fec.find_pitch(),PITCH_MAX-NDEC)

		fec.pitchbuf=s.copy()
		fec.pitchbuf[-CORRBUFLEN+PITCH_DIF]=1
		fec.pitchbuf[-CORRLEN]=1
		self.assertEqual(fec.find_pitch(),PITCH_MIN)

		fec.pitchbuf=s.copy()
		fec.pitchbuf[-CORRLEN - PITCH_MIN]=1
		fec.pitchbuf[-CORRLEN]=1
		self.assertEqual(fec.find_pitch(),PITCH_MIN)

		fec.pitchbuf=s.copy()
		fec.pitchbuf[-CORRBUFLEN+PITCH_DIF]=1
		fec.pitchbuf[-CORRLEN+PITCH_DIF+1]=1
		self.assertEqual(fec.find_pitch(),PITCH_MAX)

		fec.pitchbuf=s.copy()
		fec.pitchbuf[-CORRBUFLEN-1]=1
		fec.pitchbuf[-CORRLEN]=1
		self.assertEqual(fec.find_pitch(),PITCH_MAX)


	def test_getfespeech(self):
		fec = LowcFE()
		ori = [0]*FRAMESZ
		out = ori.copy()
		#setup internal variables
		fec.poffset = 0
		fec.pitchblen = FRAMESZ
		fec.pitchbufstart = HISTORYLEN - FRAMESZ
		fec.getfespeech(out,FRAMESZ)
		self.assertEqual(out,ori)

		fec.pitchbuf[-FRAMESZ]=1
		fec.getfespeech(out,FRAMESZ)
		ori[0]=1
		self.assertEqual(out,ori)
		fec.pitchbuf[-FRAMESZ]=0
		ori[0]=0
		out[0]=0

		fec.pitchbuf[-1]=1
		fec.getfespeech(out,FRAMESZ)
		ori[-1]=1
		self.assertEqual(out,ori)

		ori = [1,2,3]*2
		out = [0,0,0]
		fec.pitchblen=6
		fec.pitchbufstart = HISTORYLEN - 6
		fec.poffset = 0
		fec.pitchbuf[-6:]=ori.copy()
		fec.getfespeech(out,3)
		self.assertEqual(out,ori[:3])

		ori = [1,2,3]
		out = [0]*6
		fec.pitchblen=3
		fec.pitchbufstart = HISTORYLEN - 3
		fec.poffset = 0
		fec.pitchbuf[-3:]=ori.copy()
		fec.getfespeech(out,6)
		self.assertEqual(out,ori*2)

		ori = [1,2,3]
		out = [0]*6
		fec.pitchblen=3
		fec.pitchbufstart = HISTORYLEN - 3
		fec.poffset = 1
		fec.pitchbuf[-3:]=ori.copy()
		fec.getfespeech(out,6)
		self.assertEqual(out,[2,3,1,2,3,1])

	def test_overlap_add_at_end(self):
		pass

	def test_scalespeech(self):
		pass

	def test_overlap_add(self):
		x = [0,0,0,2,2,2,0,0,0]
		y = [2,2,2,0,0,0,0,0,0]
		z = [0]*9
		overlap_add(x,3,y,0,z,6,3)
		self.assertEqual(z,[0,0,0,0,0,0,2,2,2])		

	def test_dofe(self):
		#test first erasure
		fec = LowcFE()
		out = fec.dofe()
		self.assertEqual(len(out),FRAMESZ*2)
		self.assertEqual(out,b'\x00'*FRAMESZ*2)

if __name__=="__main__":
	unittest.main()
