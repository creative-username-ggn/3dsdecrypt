#Much code taken from https://github.com/roxas75/rxTools/blob/012a9c2fe99f2d421e68ae91f738b4028995ad67/tools/scripts/ncchinfo_gen.py
#Uses some bits and pieces from https://github.com/Mtgxyz2/3ds-FUSE
#Comments are for people that care about being able to read their code tommorrow :P
import os, sys, glob, struct
from Crypto.Cipher import AES
from Crypto.Util import Counter
from hashlib import sha256
from ctypes import *
from binascii import hexlify, unhexlify
import ssl
context = ssl._create_unverified_context()
import urllib

devkeys = 0 #Set to 1 to use dev keys.
if devkeys == 0:
    cmnkeys = [0x64C5FD55DD3AD988325BAAEC5243DB98, 0x4AAA3D0E27D4D728D0B1B433F0F9CBC8,
                0xFBB0EF8CDBB0D8E453CD99344371697F, 0x25959B7AD0409F72684198BA2ECD7DC6,
                0x7ADA22CAFFC476CC8297A0C7CEEEEEBE, 0xA5051CA1B37DCF3AFBCF8CC1EDD9CE02]
    key0x2C = 0xB98E95CECA3E4D171F76A94DE934C053
    key0x25 = 0xCEE7D8AB30C00DAE850EF5E382AC5AF3
    key0x18 = 0x82E9C9BEBFB8BDB875ECC0A07D474374
    key0x1B = 0x45AD04953992C7C893724A9A7BCE6182
else:
    cmnkeys = [0x55A3F872BDC80C555A654381139E153B, 0x4434ED14820CA1EBAB82C16E7BEF0C25,
                0x85215E96CB95A9ECA4B4DE601CB562C7, 0x0C767230F0998F1C46828202FAACBE4C,
                0xE02D27441DB9558BAD087FD746DF1057, 0x0412959405AA41CC7118B61E75E283AB]
    key0x2C = 0x510207515507CBB18E243DCB85E23A1D
    key0x25 = 0x81907A4B6F1B47323A677974CE4AD71B
    key0x18 = 0x304BF1468372EE64115EBD4093D84276
    key0x1B = 0x6C8B2944A0726035F941DFC018524FB6
fixedzeros = 0x00000000000000000000000000000000
fixedsys = 0x527CE630A9CA305F3696F3CDE954194B
keys = [[key0x2C, key0x25, key0x18, key0x1B], [fixedzeros, fixedsys]]

mediaUnitSize = 0x200

ncsdPartitions = [b'Main', b'Manual', b'DownloadPlay', b'Partition4', b'Partition5', b'Partition6', b'N3DSUpdateData', b'UpdateData']
tab = '    '

class ncchHdr(Structure):
    _fields_ = [
        ('signature', c_uint8 * 0x100),
        ('magic', c_char * 4),
        ('ncchSize', c_uint32),
        ('titleId', c_uint8 * 0x8),
        ('makerCode', c_uint16),
        ('formatVersion', c_uint8),
        ('formatVersion2', c_uint8),
        ('seedcheck', c_char * 4),
        ('programId', c_uint8 * 0x8),
        ('padding1', c_uint8 * 0x10),
        ('logoHash', c_uint8 * 0x20),
        ('productCode', c_uint8 * 0x10),
        ('exhdrHash', c_uint8 * 0x20),
        ('exhdrSize', c_uint32),
        ('padding2', c_uint32),
        ('flags', c_uint8 * 0x8),
        ('plainRegionOffset', c_uint32),
        ('plainRegionSize', c_uint32),
        ('logoOffset', c_uint32),
        ('logoSize', c_uint32),
        ('exefsOffset', c_uint32),
        ('exefsSize', c_uint32),
        ('exefsHashSize', c_uint32),
        ('padding4', c_uint32),
        ('romfsOffset', c_uint32),
        ('romfsSize', c_uint32),
        ('romfsHashSize', c_uint32),
        ('padding5', c_uint32),
        ('exefsHash', c_uint8 * 0x20),
        ('romfsHash', c_uint8 * 0x20),
    ]
    def __new__(cls, buf):
        return cls.from_buffer_copy(buf)
    def __init__(self, data):
        pass

class ncchSection:
    exheader = 1
    exefs = 2
    romfs = 3

class ncch_offsetsize(Structure):
    _fields_ = [
        ('offset', c_uint32),
        ('size', c_uint32),
    ]

class ncsdHdr(Structure):
    _fields_ = [
        ('signature', c_uint8 * 0x100),
        ('magic', c_char * 4),
        ('mediaSize', c_uint32),
        ('titleId', c_uint8 * 0x8),
        ('padding0', c_uint8 * 0x10),
        ('offset_sizeTable', ncch_offsetsize * 0x8),
        ('padding1', c_uint8 * 0x28),
        ('flags', c_uint8 * 0x8),
        ('ncchIdTable', c_uint8 * 0x40),
        ('padding2', c_uint8 * 0x30),
    ]

class SeedError(Exception):
        pass

class ciaReader():
    #Assumes all access is 16 byte aligned
    def __init__(self, fhandle, encrypted, titkey, cIdx, contentOff):
        self.fhandle = fhandle
        self.encrypted = encrypted
        self.name = fhandle.name
        self.cIdx = cIdx
        self.contentOff = contentOff
        self.cipher = AES.new(titkey, AES.MODE_CBC, to_bytes(cIdx, 2, 'big')+b'\x00'*14)
    def seek(self, offs):
        if offs == 0:
            self.fhandle.seek(self.contentOff)
            self.cipher.IV = to_bytes(self.cIdx, 2, 'big')+b'\x00'*14
        else:
            self.fhandle.seek(self.contentOff + offs - 16)
            self.cipher.IV = self.fhandle.read(16)
    def read(self, bytes):
        if bytes == 0:
            return ''
        data = self.fhandle.read(bytes)
        if self.encrypted:
            data = self.cipher.decrypt(data)
        return data

def from_bytes (data, endianess='big'):
    if isinstance(data, str):
        data = bytearray(data)
    if endianess == 'big':
        data = reversed(data)
    num = 0
    for offset, byte in enumerate(data):
        num += byte << (offset * 8)
    return num
def to_bytes(n, length, endianess='big'):
    h = '%x' % n
    s = ('0'*(len(h) % 2) + h).zfill(length*2).decode('hex')
    return s if endianess == 'big' else s[::-1]

def scramblekey(keyX, keyY):
    rol = lambda val, r_bits, max_bits: \
        (val << r_bits%max_bits) & (2**max_bits-1) | \
        ((val & (2**max_bits-1)) >> (max_bits-(r_bits%max_bits)))
    return rol(((rol(keyX, 2, 128) ^ keyY) + 0x1FF9E9AAC5FE0408024591DC5D52768A) & 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF, 87, 128)

def reverseCtypeArray(ctypeArray): #Reverses a ctype array and converts it to a hex string.
    return ''.join('%02X' % x for x in ctypeArray[::-1])
    #Is there a better way to do this?

def getNcchAesCounter(header, type): #Function based on code from ctrtool's source: https://github.com/Relys/Project_CTR
    counter = bytearray(b'\x00' * 16)
    if header.formatVersion == 2 or header.formatVersion == 0:
        counter[:8] = bytearray(header.titleId[::-1])
        counter[8:9] = chr(type)
    elif header.formatVersion == 1:
        x = 0
        if type == ncchSection.exheader:
            x = 0x200 #ExHeader is always 0x200 bytes into the NCCH
        if type == ncchSection.exefs:
            x = header.exefsOffset * mediaUnitSize
        if type == ncchSection.romfs:
            x = header.romfsOffset * mediaUnitSize
        counter[:8] = bytearray(header.titleId)
        for i in xrange(4):
            counter[12+i] = chr((x>>((3-i)*8)) & 0xFF)
    
    return bytes(counter)

def getNewkeyY(keyY,header,titleId):
    seeds = {}
    seedif = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'seeddb.bin')
    if os.path.exists(seedif):
        with open(seedif,'rb')as seeddb:
            seedcount = struct.unpack('<I',seeddb.read(4))[0]
            seeddb.read(12)
            for i in range(seedcount):
                key = hexlify(seeddb.read(8)[::-1])
                seeds[key] = bytearray(seeddb.read(16))
                seeddb.read(8)
    if not titleId in seeds:
        print tab + "********************************"
        print tab + "Couldn't find seed in seeddb, checking online..."
        print tab + "********************************"
        for country in ['JP', 'US', 'GB', 'KR', 'TW', 'AU', 'NZ']:
            r = urllib.urlopen("https://kagiya-ctr.cdn.nintendo.net/title/0x%s/ext_key?country=%s" % (titleId, country), context=context)
            if r.getcode() == 200:
                seeds[titleId] = r.read()
                break
    if titleId in seeds:
        seedcheck = struct.unpack('>I',header.seedcheck)[0]
        if int(sha256(seeds[titleId] + unhexlify(titleId)[::-1]).hexdigest()[:8],16) == seedcheck:
            keystr = sha256(to_bytes(keyY, 16, "big") + seeds[titleId]).hexdigest()[:32]
            newkeyY = unhexlify(keystr)
            return from_bytes(newkeyY, "big")
        else:
            raise SeedError('Seed check fail, wrong seed?')
    raise SeedError('Something Happened :/')

def align(x,y):
    mask = ~(y-1)
    return (x+(y-1))&mask
def parseCIA(fh):
    print 'Parsing CIA in file "%s":' % os.path.basename(fh.name)
    
    fh.seek(0)
    headerSize,type,version,cachainSize,tikSize,tmdSize,metaSize,contentSize=struct.unpack("<IHHIIIIQ",fh.read(0x20))
    cachainOff=align(headerSize,64)
    tikOff=align(cachainOff+cachainSize,64)
    tmdOff=align(tikOff+tikSize,64)
    contentOffs=align(tmdOff+tmdSize,64)
    metaOff=align(contentOffs+contentSize,64)
    
    fh.seek(tikOff+0x7F+0x140)
    enckey = fh.read(16)
    fh.seek(tikOff+0x9C+0x140)
    tid = fh.read(8)
    if hexlify(tid)[:5] == '00048':
        print 'Unsupported CIA file'
        return
    fh.seek(tikOff+0xB1+0x140)
    cmnkeyidx = struct.unpack('B', fh.read(1))[0]
    
    titkey = AES.new(to_bytes(cmnkeys[cmnkeyidx], 16, "big"), AES.MODE_CBC, tid+b'\x00'*8).decrypt(enckey)
    
    fh.seek(tmdOff+0x206)
    contentCount = struct.unpack('>H', fh.read(2))[0]
    nextContentOffs = 0
    for i in xrange(contentCount):
        fh.seek(tmdOff+0xB04+(0x30*i))
        cId, cIdx, cType, cSize = struct.unpack(">IHHQ", fh.read(16))
        cEnc = 1
        if cType & 0x1 == 0:
            cEnc = 0
        
        fh.seek(contentOffs+nextContentOffs)
        if cEnc:
            test = AES.new(titkey, AES.MODE_CBC, to_bytes(cIdx, 2, 'big')+b'\x00'*14).decrypt(fh.read(0x200))
        else:
            test = fh.read(0x200)
        if not test[0x100:0x104] == b'NCCH':
            print '  Problem parsing CIA content, skipping. Sorry about that :/\n'
            continue
        
        fh.seek(contentOffs+nextContentOffs)
        ciaHandle = ciaReader(fh, cEnc, titkey, cIdx, contentOffs+nextContentOffs)
        nextContentOffs = nextContentOffs + align(cSize, 64)
        
        parseNCCH(ciaHandle, cSize, 0, cIdx, tid, 0, 0)

def parseNCSD(fh):
    print 'Parsing NCSD in file "%s":' % os.path.basename(fh.name)
    
    fh.seek(0)
    header = ncsdHdr()
    fh.readinto(header) #Reads header into structure
    
    for i in xrange(len(header.offset_sizeTable)):
        if header.offset_sizeTable[i].offset:
            parseNCCH(fh, header.offset_sizeTable[i].size * mediaUnitSize, header.offset_sizeTable[i].offset * mediaUnitSize, i, reverseCtypeArray(header.titleId), 0, 1)

def parseNCCH(fh, fsize, offs=0, idx=0, titleId='', standAlone=1, fromNcsd=0):
    tab = '    ' if not standAlone else '  '
    if not standAlone and fromNcsd:
        print '  Parsing %s NCCH' % ncsdPartitions[idx]
    elif not standAlone:
        print '  Parsing NCCH %d' % idx
    else:
        print 'Parsing NCCH in file "%s":' % os.path.basename(fh.name)
    entries = 0
    data = ''
    
    fh.seek(offs)
    tmp = fh.read(0x200)
    header = ncchHdr(tmp)
    
    if titleId == '':
        titleId = reverseCtypeArray(header.programId)   #Use ProgramID instead, is it OK?
    
    ncchKeyY = from_bytes(header.signature[:16], "big")
    
    print tab + 'Product code: ' + str(bytearray(header.productCode)).rstrip('\x00')
    print tab + 'KeyY: %032X' % ncchKeyY
    print tab + 'Title ID: %s' % reverseCtypeArray(header.titleId)
    print tab + 'Format version: %d' % header.formatVersion
    
    usesExtraCrypto = bytearray(header.flags)[3]
    if usesExtraCrypto:
        print tab + 'Uses Extra NCCH crypto, keyslot 0x%X' % ({0x1: 0x25, 0xA: 0x18, 0xB: 0x1B}[usesExtraCrypto])
    
    fixedCrypto = 0
    encrypted = 1
    if (header.flags[7] & 0x1):
        fixedCrypto = 2 if (header.titleId[3] & 0x10) else 1
        print tab + 'Uses fixed-key crypto'
    if (header.flags[7] & 0x4):
        encrypted = 0
        print tab + 'Not Encrypted'
    
    useSeedCrypto = (header.flags[7] & 0x20) != 0
    
    keyY = ncchKeyY
    if useSeedCrypto:
        keyY = getNewkeyY(ncchKeyY, header, hexlify(titleId))
        print tab + 'Uses 9.6 NCCH Seed crypto with KeyY: %032X' % keyY
    
    print ''
    
    base = os.path.splitext(os.path.basename(fh.name))[0]
    base += '.%s.ncch' % (idx if (fromNcsd == 0) else ncsdPartitions[idx])
    base = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), base) #Fix drag'n'drop
    
    with open(base, 'wb') as f:
        fh.seek(offs)
        tmp = fh.read(0x200)
        tmp = tmp[:0x188+7] + chr((ord(tmp[0x188+7])&0x2)|0x4) + tmp[0x188+7+1:] #Set NCCH flag[7] to show that it is unencrypted
        f.write(tmp)
        
        if header.exhdrSize != 0:
            counter = getNcchAesCounter(header, ncchSection.exheader)
            dumpSection(f, fh, 0x200, header.exhdrSize * 2, ncchSection.exheader, counter, usesExtraCrypto, fixedCrypto, encrypted, [ncchKeyY, keyY])
        
        if header.exefsSize != 0:
            counter = getNcchAesCounter(header, ncchSection.exefs)
            dumpSection(f, fh, header.exefsOffset * mediaUnitSize, header.exefsSize * mediaUnitSize, ncchSection.exefs, counter, usesExtraCrypto, fixedCrypto, encrypted, [ncchKeyY, keyY])
        
        if header.romfsSize != 0:
            counter = getNcchAesCounter(header, ncchSection.romfs)
            dumpSection(f, fh, header.romfsOffset * mediaUnitSize, header.romfsSize * mediaUnitSize, ncchSection.romfs, counter, usesExtraCrypto, fixedCrypto, encrypted, [ncchKeyY, keyY])
    
    print ''

def dumpSection(f, fh, offset, size, type, ctr, usesExtraCrypto, fixedCrypto, encrypted, keyYs):
    cryptoKeys = {0x0: 0, 0x1 : 1, 0xA: 2, 0xB: 3}
    sections = ['ExHeader', 'ExeFS', 'RomFS']
    
    print tab + '%s offset:  %08X' % (sections[type-1], offset)
    print tab + '%s counter: %s' % (sections[type-1], hexlify(ctr))
    print tab + '%s size: %d bytes' % (sections[type-1], size)
    
    tmp = offset - f.tell()
    if tmp > 0:
        f.write(fh.read(tmp))
    
    if not encrypted:
        sizeleft = size
        while sizeleft > 4*1024*1024:
            f.write(fh.read(4*1024*1024))
            sizeleft -= 4*1024*1024
        if sizeleft > 0:
            f.write(fh.read(sizeleft))
        return
    
    key0x2C = to_bytes(scramblekey(keys[0][0], keyYs[0]), 16, "big")
    
    if type == ncchSection.exheader:
        key = key0x2C
        if fixedCrypto:
            key = to_bytes(keys[1][fixedCrypto-1], 16, "big")
        cipher = AES.new(key, AES.MODE_CTR, counter=Counter.new(128, initial_value=from_bytes(ctr, "big")))
        f.write(cipher.decrypt(fh.read(size)))
    
    if type == ncchSection.exefs:
        key = key0x2C
        if fixedCrypto:
            key = to_bytes(keys[1][fixedCrypto-1], 16, "big")
        cipher = AES.new(key, AES.MODE_CTR, counter=Counter.new(128, initial_value=from_bytes(ctr, "big")))
        exedata = fh.read(size)
        exetmp = cipher.decrypt(exedata)
        if usesExtraCrypto:
            extraCipher = AES.new(to_bytes(scramblekey(keys[0][cryptoKeys[usesExtraCrypto]], keyYs[1]), 16, "big"), AES.MODE_CTR, counter=Counter.new(128, initial_value=from_bytes(ctr, "big")))
            exetmp2 = extraCipher.decrypt(exedata)
            for i in xrange(10):
                fname,off,size=struct.unpack("<8sII",exetmp[i*0x10:(i+1)*0x10])
                off += 0x200
                if fname.strip('\x00') not in ['icon', 'banner']:
                    exetmp = exetmp[:off] + exetmp2[off:off+size] + exetmp[off+size:]
        f.write(exetmp)
    
    if type == ncchSection.romfs:
        key = to_bytes(scramblekey(keys[0][cryptoKeys[usesExtraCrypto]], keyYs[1]), 16, "big")
        if fixedCrypto:
            key = to_bytes(keys[1][fixedCrypto-1], 16, "big")
        cipher = AES.new(key, AES.MODE_CTR, counter=Counter.new(128, initial_value=from_bytes(ctr, "big")))
        sizeleft = size
        while sizeleft > 4*1024*1024:
            f.write(cipher.decrypt(fh.read(4*1024*1024)))
            sizeleft -= 4*1024*1024
        if sizeleft > 0:
            f.write(cipher.decrypt(fh.read(sizeleft)))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print 'usage: decrypt.py *file*'
        sys.exit()
    
    inpFiles = []
    existFiles = []
    
    for i in xrange(len(sys.argv)-1):
        inpFiles = inpFiles + glob.glob(sys.argv[i+1].replace('[','[[]')) #Needed for wildcard support on Windows
    
    for i in xrange(len(inpFiles)):
        if os.path.isfile(inpFiles[i]):
            existFiles.append(inpFiles[i])
    
    if existFiles == []:
        print "Input files don't exist"
        sys.exit()
    
    print ''
    
    for file in existFiles:
        with open(file,'rb') as fh:
            fh.seek(0x100)
            magic = fh.read(4)
            if magic == b'NCSD':
                result = parseNCSD(fh)
                print ''
            elif magic == b'NCCH':
                fh.seek(0, 2)
                result = parseNCCH(fh, fh.tell())
                print ''
            elif (fh.name.split('.')[-1].lower() == 'cia'):
                fh.seek(0)
                if fh.read(4) == b'\x20\x20\x00\x00':
                    parseCIA(fh)
                    print ''
    
    print 'Done!'
    raw_input('')
