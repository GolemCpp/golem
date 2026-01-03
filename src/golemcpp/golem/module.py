import os
import sys
from golemcpp.golem.project import Project
import importlib.util
import importlib.machinery


class Module:
    def __init__(self, path=None):
        self.path = '.' if path is None else path

        if sys.modules.get('__golem_project_glm__'):
            self.module = sys.modules.get('__golem_project_glm__')
        else:
            project_path = os.path.join(self.path, 'golemfile.py')
            if not os.path.exists(project_path):
                project_path = os.path.join(self.path, 'golem.py')
            if not os.path.exists(project_path):
                project_path = os.path.join(self.path, 'project.glm')
            if not os.path.exists(project_path):
                print("ERROR: can't find " + project_path)
                return
            self.load_recipe_source(project_path)

    def load_recipe_source(self, path):
        importlib.machinery.SOURCE_SUFFIXES.append('')
        spec = importlib.util.spec_from_file_location('__golem_project_glm__',
                                                      path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        importlib.machinery.SOURCE_SUFFIXES.pop()

    def project(self):

        if not hasattr(self.module, 'configure'):
            print(self.module)
            print("ERROR: no configure function found")
            return

        project = Project()
        self.module.configure(project)
        return project
