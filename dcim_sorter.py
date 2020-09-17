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

oldEnough = 30
minSpace = 1000
exts = ['dng', 'cr2', 'cr3', 'nef', '3fr', 'arq', 'crw', 'cs1', 'czi', 'dcr', 'erf', 'gpr', 'iiq', 'k25', 'kdc', 'mef', 'mrw', 'nrw', 'orf', 'pef', 'r3d', 'raw', 'rw2', 'rwl', 'rwz', 'sr2', 'srf', 'srw', 'x3f'] # files with these exntensions will be copied to raw destination
nonRawExts = ['jpg', 'jpeg', 'png', 'webp', 'heif', 'heic', 'avci', 'avif']
sidecarExts = ['pp3', 'pp2', 'arp', 'xmp']
destDir = '/Users/isaac/Raw' # where to copy raw files into directory structure
nonRawDestDir = '/Users/isaac/Pictures' # where to copy non-raw images into directory structure
pathForm = '#Model#\%Y\%Y-%m' # surround EXIF tags with #, and can use POSIX datetime place-holder
otherDirs = ['/Users/isaac/Raw/dark-frames', '/Users/isaac/Raw/flat-fields'] # directories to look for copies other than the destination directories

srcDir = sys.argv[1]
print(srcDir)

slsh = '/'
if platform.system() == 'Windows':
	slsh = '\\'

wchar = os.get_terminal_size(0).columns

def get_char(query, allowables):
	allowable = {}
	for char in allowables:
		allowable[char] = True
	while True:
		data = input("{query}:\n".format(**locals()))
		if allowable[data[-1]]:
			break
	return data

def press_enter_to_exit():
	get_char("press ENTER to exit", [chr(13)])
	exit()

# check if a destination contains source or source contains a destination
destPath = destDir.split(slsh)
nonRawDestPath = nonRawDestDir.split(slsh)
srcPath = srcDir.split(slsh)
srcContainsDest = True
destContainsSrc = True
for i in range(0, max(len(srcPath), len(destPath), len(nonRawDestPath))):
	if i < len(destPath):
		ddir = destPath[i]
	else:
		ddir = ''
	if i < len(nonRawDestPath):
		nrddir = nonRawDestPath[i]
	else:
		nrddir = ''
	if i < len(srcPath):
		sdir = srcPath[i]
	else:
		sdir = ''
	# print(i, sdir, ddir, nrddir)
	if ddir != sdir and nrddir != sdir:
		if i < len(srcPath):
			srcContainsDest = False
		if i < len(destPath):
			destContainsSrc = False
		if i < len(nonRawDestPath):
			destContainsSrc = False
if destContainsSrc or srcContainsDest:
	if srcContainsDest:
		print("source directory contains or is the same as a destination directory")
	elif destContainsSrc:
		print("a destination directory contains or is the same as source directory")
	print("source: \t\t{srcDir}\ndestination: \t\t{destDir}\nnon-raw destination: \t{nonRawDestDir}".format(**locals()))
	press_enter_to_exit()

exit()

# create extension hashes
validExts = {}
validNonRawExts = {}
for ext in exts:
	validExts['.' + ext.upper()] = True
for ext in nonRawExts:
	validNonRawExts['.' + ext.upper()] = True

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
	if not os.path.isfile(filepath):
		return
	f = open(filepath)
	tags = exifread.process_file(f, details=False, stop_tag='DateTimeOriginal')
	if 'DateTimeOriginal' in tags.keys():
		spaced = tags["Image Orientation"].split(' ')
		year, month, mday = spaced[0].split(':')
		hour, minute, second = spaced[1].split(':')
		return datetime.datetime(year, month, mday, hour, minute, second)
	else:
		return os.path.getmtime(filepath)

def parse_format_string(format, dt, filepath):
	formatted = dt.strftime(format)
	tags = {}
	with open(filepath, 'rb') as f:
		tags = exifread.process_file(f, details=False)
	for tag in tags.keys():
		value = tags[tag]
		search = '#' + tag + '#'
		formatted.replace(search, value)
	return formatted

def delete_sidecars(filepath):
	pathAndName = re.match('.*(?=\.)', filepath)
	for scExt in sidecarExts:
		sidecarFiles = [filepath + '.' + scExt, pathAndName + '.' + scExt]
		for scf in sidecarFiles:
			if os.path.isfile(scf):
				print('X ' + scf)
				os.remove(scf)

def delete_image(filepath):
	print('X ' + filepath)
	os.remove(filepath)
	delete_sidecars(filepath)
	path = re.match('.*(?=\\)', filepath)
	potentiallyEmptyPathYes[path] = True

def process_file(file, srcFile):
	ext = re.match('(\.[^.]+)$', file)
	pathAndName = re.match('.*(?=\.)', srcFile)
	if validExts[ext.upper()] or validNonRawExts[ext.upper()]:
		fileCount = fileCount + 1
		srcDT = image_datetime(srcFile)
		if fileCount == 1:
			oldestDT = srcDT
			newestDT = srcDT
		if srcDT < oldestDT:
			oldestDT = srcDT
		if srcDT > newestDT:
			newestDT = srcDT
		destSubPath = parse_format_string(pathForm, srcDT, srcFile)
		destPath = ''
		if validNonRawExts[ext.upper()]:
			destPath = nonRawDestDir + slsh + destSubPath
		else:
			destPath = destDir + slsh + destSubPath
		destFile = destPath + slsh + file
		destPathAndName = re.match('.*(?=\.)', destFile)
		found = False
		dirs = [destPath] + otherDirs
		for d in dirs:
			lookFile = d + slsh + file
			if os.path.isfile(lookFile) and os.path.getsize(lookFile) == os.path.getsize(srcFile) and srcDT == image_datetime(lookFile):
				found = True
				break
		if found:
			ago = nowDT - srcDT
			if ago.days > oldEnough:
				safeOldImageCount = safeOldImageCount + 1
				safeOldImagesExist[srcFile] = True
			datesBySafeImageFilepaths[srcFile] = srcDT
			dupeCount = dupeCount + 1
			if dotStr != '':
				if len(dotStr) == wchar:
					dotStr = ''
				print("\033[F", end = '')
			dotStr = dotStr + '.'
			print(dotStr)
		else:
			# if file not found in destination, make directories and copy it
			print(srcFile)
			print('-> ' + destFile)
			dotStr = ''
			os.makedirs(destPath)
			copyfile(srcFile, destFile)
			datesByCopiedFiles[destFile] = srcDT
			sourcesByCopiedFiles[destFile] = srcFile
			copyCount = copyCount + 1
		# copy sidecars if present
		for scExt in sidecarExts:
			sidecarFiles = [srcFile + '.' + scExt, pathAndName + '.' + scExt]
			destSidecarFiles = [destFile + '.' + scExt, destPathAndName]
			for i in range(0, len(sidecarFiles)):
				scf = sidecarFiles[i]
				dscf = destSidecarFiles[i]
				if not os.path.isfile(dscf):
					print(scf)
					print('-> ' + dscf)
					dotStr = ''
					copyfile(scf, dscf)


files = glob.glob(srcDir + slsh + '**' + slsh + '*', recursive = True) 
for filepath in files:
	file = re.match('[^\\/:*?"<>|\r\n]+$', filepath)
	print(filepath)
	# process_file(file, filepath)