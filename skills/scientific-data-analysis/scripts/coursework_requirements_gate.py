#!/usr/bin/env python3
from _internal.child_skill_dispatch import main as _dispatch_main,load_child_module as L
if __name__=="__main__":raise SystemExit(_dispatch_main(__file__,"scientific-data-maintainer"))
m=L(__file__,"scientific-data-maintainer")
if m:globals().update({k:v for k,v in vars(m).items() if not k.startswith("_")})# if not _name.startswith("_"):
