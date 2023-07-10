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
        ("../XTVirtualHEStain.py", "VirtualHEStainDialog"),
        ("../XTConfigureChannelSettings.py", "ConfigureChannelSettingsDialog"),
        ("../XTExportChannelSettings.py", "ExportChannelSettingsDialog"),
    ]
]

# Create the index.html file, make the urls relative so
# website is self contained (in the README.md they are
# absolute as the website is on a different branch).
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.system(
    f'pandoc -s ../README.md -o index.html -c {css_file_name} --metadata title="SimpleITK Imaris Extensions"'
)
url_prefix = "http://niaid.github.io/imaris_extensions/"
with open("index.html", "r") as fp:
    index_html = fp.read()
for f, a in extensions_information:
    local_url = os.path.split(f)[1][:-3] + ".html"
    index_html = index_html.replace(url_prefix + local_url, local_url, 1)
with open("index.html", "w") as fp:
    fp.write(index_html)


# Create the html files for all extensions.
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
            rst_content = inspect.getdoc(getattr(module, attribute_name))
            # update all paths to images and write to file
            fp.write(rst_content.replace("docs/images", "../docs/images"))
            fp.flush()
            os.system(f"pandoc -s {fp.name} -o {f_name[:-3]}.html -c {css_file_name}")
