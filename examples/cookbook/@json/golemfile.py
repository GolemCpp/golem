def configure(project):

    project.export(
        name="json",
        includes=["single_include"],
        header_only=True,
        licenses=["LICENSE.MIT"],
    )
