def configure(project):

    project.export(
        name="gsl",
        includes=["include"],
        header_only=True,
        licenses=["LICENSE", "ThirdPartyNotices.txt"],
    )
