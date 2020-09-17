import fnmatch
import os
import sys
import platform
import datetime
import os.path
import exifread
import re
from shutil import copyfile
import glob
import pathlib

oldEnough = 30
minSpace = 1000
exts = ['dng', 'cr2', 'cr3', 'nef', '3fr', 'arq', 'crw', 'cs1', 'czi', 'dcr', 'erf', 'gpr', 'iiq', 'k25', 'kdc', 'mef', 'mrw', 'nrw', 'orf', 'pef', 'r3d', 'raw', 'rw2', 'rwl', 'rwz', 'sr2', 'srf', 'srw', 'x3f'] # files with these exntensions will be copied to raw destination
nonRawExts = ['jpg', 'jpeg', 'png', 'webp', 'heif', 'heic', 'avci', 'avif']
sidecarExts = ['pp3', 'pp2', 'arp', 'xmp']
destDir = '/Users/isaac/Raw' # where to copy raw files into directory structure
nonRawDestDir = '/Users/isaac/Pictures' # where to copy non-raw images into directory structure
pathForm = '#Model#\%Y\%Y-%m' # surround EXIF tags with #, and can use POSIX datetime place-holder
otherDirs = ['/Users/isaac/Raw/dark-frames', '/Users/isaac/Raw/flat-fields'] # directories to look for copies other than the destination directories

destPath = pathlib.Path(destDir)
nonRawDestPath = pathlib.Path(nonRawDestDir)
otherPaths = []
for d in otherDirs:
	otherPaths.append(pathlib.Path(d))
srcPath = pathlib.Path(sys.argv[1])
print(str(srcPath))

wchar = os.get_terminal_size(0).columns

def get_char(query, allowables):
	allowable = {}
	for char in allowables:
		allowable[char] = True
	while True:
		data = input("{query}:\n".format(**locals()))
		if len(data) > 0 and allowable[data[-1]]:
			break
	return data

def press_enter_to_exit():
	input("press ENTER to exit:")
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

exit()

# create extension hashes
validExts = {}
validNonRawExts = {}
for ext in exts:
	validExts[ext.upper()] = True
for ext in nonRawExts:
	validNonRawExts[ext.upper()] = True

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

def image_datetime(filepath):
	if not filepath.is_file():
		return
	f = filepath.open()
	tags = exifread.process_file(f, details=False, stop_tag='DateTimeOriginal')
	if 'DateTimeOriginal' in tags.keys():
		spaced = tags["Image Orientation"].split(' ')
		year, month, mday = spaced[0].split(':')
		hour, minute, second = spaced[1].split(':')
		return datetime.datetime(year, month, mday, hour, minute, second)
	else:
		return os.path.getmtime(str(filepath))

def parse_format_string(format, dt, filepath):
	formatted = dt.strftime(format)
	tags = {}
	with filepath.open('rb') as f:
		tags = exifread.process_file(f, details=False)
	for tag in tags.keys():
		value = tags[tag]
		search = '#' + tag + '#'
		formatted.replace(search, value)
	return formatted

def delete_sidecars(filepath):
	for scExt in sidecarExts:
		sidecarFiles = [pathlib.Path(str(filepath) + '.' + scExt), pathlib.Path(filepath.parent / filepath.stem + '.' + scExt)]
		for scf in sidecarFiles:
			if scf.is_file():
				print('X ' + str(scf))
				scf.unlink()

def delete_image(filepath):
	delete_sidecars(filepath)
	print('X ' + str(filepath))
	filepath.unlink()
	potentiallyEmptyPathYes[filepath.parent] = True

def process_file(filepath):
	ext = filepath.suffix
	ext = ext.upper()
	if validExts[ext] or validNonRawExts[ext]:
		fileCount = fileCount + 1
		srcDT = image_datetime(str(filepath))
		if fileCount == 1:
			oldestDT = srcDT
			newestDT = srcDT
		if srcDT < oldestDT:
			oldestDT = srcDT
		if srcDT > newestDT:
			newestDT = srcDT
		destSubPath = parse_format_string(pathForm, srcDT, filepath)
		destStr = ''
		if validNonRawExts[ext]:
			destStr = nonRawDestPath / destSubPath
		else:
			destStr = destPath / destSubPath
		destFile = pathlib.PurePath(destStr / filepath.name)
		found = False
		paths = [pathlib.PurePath(destStr)] + otherPaths
		for p in paths:
			look = pathlib.Path(p / filepath.name)
			if look.is_file() and look.stat().st_size == filepath.stat().st_size and srcDT == image_datetime(look):
				found = True
				break
		if found:
			ago = nowDT - srcDT
			if ago.days > oldEnough:
				safeOldImageCount = safeOldImageCount + 1
				safeOldImagesExist[str(filepath)] = True
			datesBySafeImageFilepaths[str(filepath)] = srcDT
			dupeCount = dupeCount + 1
			if dotStr != '':
				if len(dotStr) == wchar:
					dotStr = ''
				print("\033[F", end = '')
			dotStr = dotStr + '.'
			print(dotStr)
		else:
			# if file not found in destination, make directories and copy it
			print(str(filepath))
			print('-> ' + str(destFile))
			dotStr = ''
			os.makedirs(destFile.parent)
			copyfile(str(filepath), str(destFile))
			datesByCopiedFiles[str(destFile)] = srcDT
			sourcesByCopiedFiles[str(destFile)] = str(filepath)
			copyCount = copyCount + 1
		# copy sidecars if present
		for scExt in sidecarExts:
			sidecarFiles = [str(filepath) + '.' + scExt, filepath.parent / filepath.stem + '.' + scExt]
			destSidecarFiles = [str(destFile) + '.' + scExt, destFile.parent / destFile.stem + '.' + scExt]
			for i in range(0, len(sidecarFiles)):
				scf = pathlib.Path(sidecarFiles[i])
				dscf = pathlib.Path(destSidecarFiles[i])
				if not dscf.is_file():
					print(str(scf))
					print('-> ' + str(dscf))
					dotStr = ''
					copyfile(str(scf), str(dscf))


files = srcPath.glob('**/*', recursive = True) 
for filepath in files:
	print(filepath)
	# process_file(filepath)