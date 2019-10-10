import os
import sys
import imp
from project import Project


class Module:
    def __init__(self, path=None):
        self.path = '.' if path is None else path

        if sys.modules.get('project_glm'):
            self.module = sys.modules.get('project_glm')
        else:
            project_path = os.path.join(self.path, 'golemfile.py')
            if not os.path.exists(project_path):
                project_path = os.path.join(self.path, 'golem.py')
            if not os.path.exists(project_path):
                project_path = os.path.join(self.path, 'project.glm')
            if not os.path.exists(project_path):
                print "ERROR: can't find " + project_path
                return
            self.module = imp.load_source('project_glm', project_path)

    def project(self):

        if not hasattr(self.module, 'configure'):
            print(self.module)
            print "ERROR: no configure function found"
            return

        project = Project()
        self.module.configure(project)
        return project

    def script(self, context):

        # if not hasattr(self.module, 'script'):
        #	print "ERROR: no script function found"
        #	return

        if hasattr(self.module, 'script'):
            self.module.script(context)
