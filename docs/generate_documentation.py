import os
import sys
import tempfile
import inspect
import importlib

css_file_name = "midnight-green.css"
file_dir_path = os.path.dirname(os.path.abspath(__file__))
extensions_information = [
    (os.path.abspath(os.path.join(file_dir_path, f)), a)
    for f, a in [
        ("../XTChannelArithmetic.py", "ChannelArithmeticDialog"),
        ("../XTRegisterSameChannel.py", "RegisterSameChannelDialog"),
    ]
]

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.system(
    f'pandoc -s ../README.md -o index.html -c {css_file_name} --metadata title="SimpleITK Imaris Extensions"'
)

all_paths = set([os.path.dirname(d) for d, a in extensions_information])
for p in all_paths:
    sys.path.append(p)
with open(css_file_name, "r") as fp:
    css_str = fp.read()

with tempfile.TemporaryDirectory() as tmpdirname:
    for file_name, attribute_name in extensions_information:
        f_dir, f_name = os.path.split(os.path.abspath(file_name))
        spec = importlib.util.spec_from_file_location(
            f_name[:-3], os.path.abspath(file_name)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with open(os.path.join(tmpdirname, f_name[:-3] + ".rst"), "w") as fp:
            fp.write(inspect.getdoc(getattr(module, attribute_name)))
            fp.flush()
            os.system(f"pandoc -s {fp.name} -o {f_name[:-3]}.html -c {css_file_name}")
