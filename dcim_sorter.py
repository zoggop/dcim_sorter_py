import os
import sys
import datetime
import exifread
import re
from shutil import copyfile
import pathlib

# configuration:
destDir = '/Users/isaac/Raw' # where to copy raw files into directory structure
nonRawDestDir = '/Users/isaac/Pictures' # where to copy non-raw images into directory structure
otherDirs = ['/Users/isaac/Raw/dark-frames', '/Users/isaac/Raw/flat-fields'] # directories to look for copies other than the destination directories
askToDeleteAll = True # ask to delete all images from source after copying. overrides oldEnough and minSpace
oldEnough = 30 # beyond this many days old, files can be deleted from source if they're present in destination
minSpace = 1000 # MB less than this much space (in megabytes) on the source drive, you'll be asked if you want to delete some of the oldest images
pathForm = '#Image Model#/%Y/%Y-%m' # surround EXIF tags with #, and use POSIX datetime place-holders
exts = ['dng', 'cr2', 'cr3', 'nef', '3fr', 'arq', 'crw', 'cs1', 'czi', 'dcr', 'erf', 'gpr', 'iiq', 'k25', 'kdc', 'mef', 'mrw', 'nrw', 'orf', 'pef', 'r3d', 'raw', 'rw2', 'rwl', 'rwz', 'sr2', 'srf', 'srw', 'x3f'] # files with these exntensions will be copied to raw destination
nonRawExts = ['jpg', 'jpeg', 'png', 'webp', 'heif', 'heic', 'avci', 'avif']
sidecarExts = ['pp3', 'pp2', 'arp', 'xmp']


destPath = pathlib.Path(destDir)
nonRawDestPath = pathlib.Path(nonRawDestDir)
otherPaths = []
for d in otherDirs:
	otherPaths.append(pathlib.Path(d))
srcPath = pathlib.Path(sys.argv[1])
print(str(srcPath))

wchar = os.get_terminal_size(0).columns

minSpaceBytes = minSpace * 1000000

def format_bytes(size):
    # 2**10 = 1024
    power = 2**10
    n = 0
    power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    if size < 10:
    	size = round(size, 1)
    else:
    	size = int(size)
    return str(size) + ' ' + power_labels[n]+'B'

def press_enter_to_exit():
	input("press ENTER to exit")
	exit()

# check if a destination contains source or source contains a destination
srcContainsDest = True
destContainsSrc = True
for i in range(0, max(len(srcPath.parts), len(destPath.parts), len(nonRawDestPath.parts))):
	if i < len(destPath.parts):
		dseg = destPath.parts[i]
	else:
		dseg = ''
	if i < len(nonRawDestPath.parts):
		nrdseg = nonRawDestPath.parts[i]
	else:
		nrdseg = ''
	if i < len(srcPath.parts):
		sseg = srcPath.parts[i]
	else:
		sseg = ''
	if dseg != sseg and nrdseg != sseg:
		if i < len(srcPath.parts):
			srcContainsDest = False
		if i < len(destPath.parts):
			destContainsSrc = False
		if i < len(nonRawDestPath.parts):
			destContainsSrc = False
if destContainsSrc or srcContainsDest:
	if srcContainsDest:
		print("source directory contains or is the same as a destination directory")
	elif destContainsSrc:
		print("a destination directory contains or is the same as source directory")
	print("source: \t\t{srcPath}\ndestination: \t\t{destPath}\nnon-raw destination: \t{nonRawDestPath}".format(**locals()))
	press_enter_to_exit()

# create extension hashes
validExts = {}
validNonRawExts = {}
for ext in exts:
	validExts['.' + ext.upper()] = True
for ext in nonRawExts:
	validNonRawExts['.' + ext.upper()] = True

# tags that the formatter needs to look for
formatTags = re.findall('#(.*?)#', pathForm)

fileCount = 0
dupeCount = 0
copyCount = 0
safeOldImageCount = 0

safeOldImagesExist = {}
datesBySafeImageFilepaths = {}
datesByCopiedFiles = {}
sourcesByCopiedFiles = {}
potentiallyEmptyPathYes = {}

nowDT = datetime.datetime.now()
oldestDT = nowDT
newestDT = nowDT

dotStr = ''

def get_safe_datetime(fileStr):
	return datesBySafeImageFilepaths.get(fileStr)

def image_datetime(filepath):
	if not filepath.is_file():
		return
	f = filepath.open(mode='rb')
	# tags = exifread.process_file(f, details=False, stop_tag='DateTimeOriginal')
	tags = exifread.process_file(f, stop_tag='EXIF DateTimeOriginal', details=False)
	if 'EXIF DateTimeOriginal' in tags.keys():
		values = tags['EXIF DateTimeOriginal'].values.split(' ')
		year, month, mday = values[0].split(':')
		hour, minute, second = values[1].split(':')
		# print(year, month, mday, hour, minute, second)
		return datetime.datetime(int(year), int(month), int(mday), int(hour), int(minute), int(second))
	else:
		return datetime.datetime.fromtimestamp(filepath.stat().st_mtime)

def parse_format_string(form, dt, filepath):
	formatted = dt.strftime(form)
	tags = {}
	f = filepath.open(mode='rb')
	if len(formatTags) == 1:
		tags = exifread.process_file(f, stop_tag=formatTags[0], details=False)
	else:
		tags = exifread.process_file(f, details=False)
	# print(ftags)
	for tag in formatTags:
		valObj = tags.get(tag)
		if valObj:
			valStr = ''.join(str(v) for v in valObj.values)
			search = '#' + tag + '#'
			# print(search, valStr)
			formatted = formatted.replace(search, valStr)
	return formatted

def delete_sidecars(filepath):
	for scExt in sidecarExts:
		sidecarFiles = [pathlib.Path(str(filepath) + '.' + scExt), pathlib.Path(str(filepath.parent / filepath.stem) + '.' + scExt)]
		for scf in sidecarFiles:
			if scf.is_file():
				print('X ' + str(scf))
				scf.unlink()

def delete_image(filepath):
	delete_sidecars(filepath)
	print('X ' + str(filepath))
	filepath.unlink()
	potentiallyEmptyPathYes[str(filepath.parent)] = True

def process_file(filepath):
	global fileCount, copyCount, dupeCount, safeOldImageCount, dotStr, oldestDT, newestDT
	ext = filepath.suffix
	ext = ext.upper()
	if validExts.get(ext) or validNonRawExts.get(ext):
		fileCount += 1
		srcDT = image_datetime(filepath)
		if fileCount == 1:
			oldestDT = srcDT
			newestDT = srcDT
		if srcDT < oldestDT:
			oldestDT = srcDT
		if srcDT > newestDT:
			newestDT = srcDT
		destSubPath = parse_format_string(pathForm, srcDT, filepath)
		destStr = ''
		if validNonRawExts.get(ext):
			destStr = str(nonRawDestPath / destSubPath)
		else:
			destStr = str(destPath / destSubPath)
		destPP = pathlib.PurePath(destStr)
		destFile = pathlib.PurePath(destPP / filepath.name)
		found = False
		paths = [destPP] + otherPaths
		for p in paths:
			look = pathlib.Path(p / filepath.name)
			if look.is_file() and look.stat().st_size == filepath.stat().st_size and srcDT == image_datetime(look):
				found = True
				break
		if found:
			ago = nowDT - srcDT
			if ago.days > oldEnough:
				safeOldImageCount += 1
				safeOldImagesExist[str(filepath)] = True
			datesBySafeImageFilepaths[str(filepath)] = srcDT
			dupeCount += 1
			if dotStr != '':
				if len(dotStr) == wchar:
					dotStr = ''
					print('')
				print("\033[F", end = '')
			dotStr = dotStr + '.'
			print(dotStr)
		else:
			# if file not found in destination, make directories and copy it
			print(str(filepath))
			print('-> ' + str(destFile))
			dotStr = ''
			os.makedirs(destFile.parent, exist_ok=True)
			copyfile(str(filepath), str(destFile))
			datesByCopiedFiles[str(destFile)] = srcDT
			sourcesByCopiedFiles[str(destFile)] = str(filepath)
			copyCount += 1
		# copy sidecars if present
		for scExt in sidecarExts:
			sidecarFiles = [str(filepath) + '.' + scExt, str(filepath.parent / filepath.stem) + '.' + scExt]
			destSidecarFiles = [str(destFile) + '.' + scExt, str(destFile.parent / destFile.stem) + '.' + scExt]
			for i in range(0, len(sidecarFiles)):
				scf = pathlib.Path(sidecarFiles[i])
				dscf = pathlib.Path(destSidecarFiles[i])
				if scf.is_file() and not dscf.is_file():
					print(str(scf))
					print('-> ' + str(dscf))
					dotStr = ''
					copyfile(str(scf), str(dscf))


# process files in source directory
files = srcPath.glob('**/*')
for filepath in files:
	# print(filepath, filepath.parent, filepath.name)
	process_file(filepath)

print(fileCount, 'images found in source,', dupeCount, 'copies found in destination,', copyCount, 'copied')
if fileCount > 0:
	oldestStrf = oldestDT.strftime('%F %H:%M')
	newestStrf = newestDT.strftime('%F %H:%M')
	print('images found span from ' + oldestStrf + ' to ' + newestStrf)
else:
	press_enter_to_exit()

# check copied files and add to safe to delete list if okay
for destStr in sourcesByCopiedFiles.keys():
	destFile = pathlib.Path(destStr)
	srcStr = sourcesByCopiedFiles[destStr]
	srcFile = pathlib.Path(srcStr)
	srcDT = datesByCopiedFiles[destStr]
	if destFile.is_file() and srcFile.stat().st_size == destFile.stat().st_size and srcDT ==image_datetime(destFile):
		ago = nowDT - srcDT
		# print(" $days days old ");
		if ago.days > oldEnough:
			safeOldImageCount += 1
			safeOldImagesExist[srcStr] = True
		datesBySafeImageFilepaths[srcStr] = srcDT

# ask to delete all copied images from source if askToDeleteAll is set to true
didDeleteAll = False
if askToDeleteAll:
	yes = input('Delete all safely copied images from source? (y/N)')
	if len(yes) > 0 and yes.upper() == 'Y':
		for fpStr in datesBySafeImageFilepaths.keys():
			fp = pathlib.Path(fpStr)
			delete_image(fp)
		didDeleteAll = True


# check space on source drive if different, and potentially free up space by deleting old images
# print(srcPath.stat().st_dev, destPath.stat().st_dev)
if didDeleteAll == False and srcPath.stat().st_dev != destPath.stat().st_dev:
	st = os.statvfs(str(srcPath))
	free = st.f_bavail * st.f_frsize
	total = st.f_blocks * st.f_frsize
	used = (st.f_blocks - st.f_bfree) * st.f_frsize
	# print('free:', format_bytes(free), "total:", format_bytes(total), 'used:', format_bytes(used))
	if free < minSpaceBytes:
		print(format_bytes(total), 'total on source device')
		print(format_bytes(free), 'free on source device')
		wanted = minSpaceBytes - free
		yes = input('less than ' +  format_bytes(minSpaceBytes) + ' free on source device. Would you like to delete the oldest safely copied images to free up ' + format_bytes(wanted) + '? (y/N)')
		if len(yes) > 0 and yes.upper() == 'Y':
			safeFPStrs = []
			for fpStr in datesBySafeImageFilepaths.keys():
				safeFPStrs.append(fpStr)
			safeFPStrs.sort(key=get_safe_datetime)
			deletedBytes = 0
			for fpStr in safeFPStrs:
				if safeOldImagesExist.get(fpStr):
					safeOldCount -= 1
					safeOldImagesExist[fpStr] = False
				fp = pathlib.Path(fpStr)
				fpBytes = fp.stat().st_size
				delete_image(fp)
				deletedBytes = deletedBytes + fpBytes
				free = free + fpBytes
				if free > minSpaceBytes:
					break
			print('deleted', format_bytes(deletedBytes), 'of the oldest safely copied images.', format_bytes(free), 'now available on source device')

# ask to delete safely copied files if old enough
if didDeleteAll == False and safeOldImageCount > 0:
	yes = input('delete ' + str(safeOldImageCount) + ' safely copied images older than ' + str(oldEnough) + ' days from source? (y/N)')
	if len(yes) > 0 and yes[0].upper() == 'Y':
		deletedCount = 0
		for fileStr in safeOldImagesExist.keys():
			if safeOldImagesExist.get(fileStr):
				print('X ' + fileStr)
				delete_image(pathlib.Path(fileStr))
				deletedCount += 1
		print(deletedCount, 'images deleted from source')

# remove empty paths
for pathStr in potentiallyEmptyPathYes.keys():
	path = pathlib.Path(pathStr)
	if path.is_dir():
		count = 0
		for child in path.iterdir():
			count += 1
			break
		if count == 0:
			print('X ' + pathStr)
			path.rmdir()
		# else:
			# print(pathStr + ' is not empty, cannot remove')

press_enter_to_exit()