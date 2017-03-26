#!/usr/bin/python

import os
import sys
import re

property_seperator = '='

def print_error(msg):
    print "[ERROR] %s" % msg
    sys.exit(1)

def print_usage():
    print "[USAGE] python migrate_gradle.py {project_folder_path}"

def read_property_file(f):
    props = {}
    for line in f:
        if property_seperator in line and (not line.strip().startswith("#")):
            name, value = line.split(property_seperator, 1)
            props[name.strip()] = value.strip()
    return props

def get_bool_value_from_props(props, name, default = False):
    if name in props:
        return props[name] == "true"
    else:
        return default

def get_string_value_from_props(props, name, default = None):
    if name in props:
        return props[name]
    else:
        return default

def get_android_dependencies(props):
    android_dependencies = []
    i = 1
    while ("android.library.reference.%d" % i) in props:
        android_dependencies.append(props["android.library.reference.%d" % i])
        i = i + 1
    return android_dependencies

def replace_single_line_with_property(line, key, props):
    value = props[key]
    if type(value) is list:
        head_white_space = ""
        while len(head_white_space) < len(line) and line[len(head_white_space)] == " ":
            head_white_space = head_white_space + " "

        lines = []
        for single_value in value:
            if len(lines) == 0:
                lines.append(re.sub(r"##%s##" % key, "%s" % single_value, line))
            else:
                lines.append("%s%s" % (head_white_space, single_value))
        return lines
    else:
        return re.sub(r"##%s##" % key, "%s" % value, line)

def replace_line_with_property(line, key, props):
    if type(line) is list:
        lines = []
        for single_line in line:
            lines.extend(replace_single_line_with_property(single_line, key, props))
        return lines
    else:
        return replace_single_line_with_property(line, key, props)

def read_template_lines_by_replacing_props(template_path, props):
    if not os.path.exists(template_path):
        print_error("template file not found: %s" % template_path)
        return

    template_file = open(template_path)
    out_lines = []
    for line in template_file:
        replaced_lines = [line]
        groups = re.findall(r'##(\w+)##', line)
        if (not groups == None) and len(groups) > 0:
            for group in groups:
                if group in props:
                    replaced_lines = replace_line_with_property(replaced_lines, group, props)
        out_lines.extend(replaced_lines)

    template_file.close()
    return out_lines

def handle_project_properties_file(file_path, local_dict):
    if not os.path.exists(file_path):
        print_error("invalid android project: project.properties file not found: %s" % file_path)
        return

    project_property_file = open(file_path)
    project_property_props = read_property_file(project_property_file)
    project_property_file.close()

    local_dict["module_android_library"] = get_bool_value_from_props(project_property_props, "android.library")
    local_dict["module_target"] = get_string_value_from_props(project_property_props, "target")
    local_dict["module_proguard_cfg"] = get_string_value_from_props(project_property_props, "proguard.cfg")
    local_dict["module_dex_force_jumbo"] = get_bool_value_from_props(project_property_props, "dex.force.jumbo")

    deps = get_android_dependencies(project_property_props)
    local_dict["module_deps"] = deps

def travesal_project_properties_from_dir(dir_path, global_dict):
    if global_dict == None:
        return

    if dir_path in global_dict:
        return

    global_dict[dir_path] = {}
    global_dict[dir_path]["module_name"] = os.path.basename(os.path.abspath(dir_path))

    # retrieve project.properties
    project_property_path = os.path.join(dir_path, "project.properties")
    handle_project_properties_file(project_property_path, global_dict[dir_path])

    # travesal dependencies
    for dep_path in global_dict[dir_path]["module_deps"]:
        travesal_project_properties_from_dir(os.path.join(dir_path, dep_path), global_dict)

def generate_module_build_gradle_file(dir_path, local_dict):
    module_props_for_replace = {}

    module_dependency_list = []
    for dep_path in local_dict["module_deps"]:
        module_dependency_list.append("compile project(':%s')" % _global_module_property_dict[os.path.join(dir_path, dep_path)]["module_name"])
    module_props_for_replace["module_dependencies"] = module_dependency_list

    generated_lines = []

    if local_dict["module_android_library"]:
        generated_lines = read_template_lines_by_replacing_props(os.path.join(os.path.dirname(__file__), "./templates/build.gradle.template.library"), module_props_for_replace)
    else:
        root_template_file = open(os.path.join(os.path.dirname(__file__), "./templates/build.gradle.template.root"))
        for line in root_template_file:
            generated_lines.append(line)
        root_template_file.close()
        generated_lines.append("\n")
        generated_lines.extend(read_template_lines_by_replacing_props(os.path.join(os.path.dirname(__file__), "./templates/build.gradle.template.application"), module_props_for_replace))
        for line in generated_lines:
            print line

def migrate_main_module_dir():
    global _global_module_property_dict
    _global_module_property_dict = {}
    travesal_project_properties_from_dir(_global_main_module_folder_path, _global_module_property_dict)

    main_module_setting_gradle_path = os.path.join(_global_main_module_folder_path, "settings.gradle")
    main_module_setting_gradle_file = open(main_module_setting_gradle_path, "w")
    main_module_setting_gradle_file.write("rootProject.projectDir = file('.')\n")
    main_module_setting_gradle_file.write("\n")
    for module_path in _global_module_property_dict.keys():

        # write settings.gradle
        module_name = _global_module_property_dict[module_path]["module_name"]
        main_module_setting_gradle_file.write("include ':%s'\n" % module_name)
        main_module_setting_gradle_file.write("project(':%s').projectDir = file('%s')\n" % (module_name, os.path.relpath(module_path, _global_main_module_folder_path)))
        main_module_setting_gradle_file.write("\n")

        # write build.gradle
        generate_module_build_gradle_file(module_path, _global_module_property_dict[module_path])

    main_module_setting_gradle_file.close()


def main():
    global _global_main_module_folder_path
    global _global_created_files
    _global_created_files = []
    if len(sys.argv) < 2:
        print_usage()
        return

    _global_main_module_folder_path = sys.argv[1]
    if not os.path.exists(_global_main_module_folder_path):
        print_usage()
        return

    migrate_main_module_dir()

if __name__ == '__main__':
    main()
