[app]

title = 双色球选号
package.name = ssq
package.domain = org.lottery
source.dir = .

source.include_exts = py,png,jpg,kv,atlas,ttf
source.exclude_exts = spec

version = 1.0
requirements = python3,kivy,requests,matplotlib,numpy,pil
orientation = portrait
osx.python_version = 3
osx.kivy_version = 2.3.0

fullscreen = 0
permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.archs = arm64-v8a,armeabi-v7a
android.accept_sdk_licenses = True
log_level = 2
warn_on_root = 0

[buildozer]
arch = arm64-v8a,armeabi-v7a
osx.rootdir = .

