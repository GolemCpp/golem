def configure(project):

    project.library(
        name="mylib",
        includes=["mylib/include"],
        source=["mylib/src"],
        defines=["FOO_API_EXPORT"],
    )

    project.export(name="mylib", includes=["mylib/include"], defines=["FOO_API_IMPORT"])

    # Here we use @json to refer to the recipe declared in the cookbook living beside
    # this project. But the default cookbook has an equivalent recipe reachable with
    # @json@nlohmann.
    project.program(name="hello-minimal", source=["src"], use=["mylib"], deps=["@json"])
