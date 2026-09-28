"""CAP's persisted GraphQL query bodies. DO NOT REFORMAT.

CAP's /graphql endpoint enforces a persisted-query safelist: it rejects any
operation whose body it does not recognise, with `QUERY_NOT_IN_SAFELIST`. These
strings were captured from CAP's web client and must stay byte-for-byte
identical -- reformatting them, even whitespace, even dropping `__typename`,
breaks them.

If CAP redeploys with changed queries, regenerate with `cap recover-queries`
(see cap_client.recover) or re-capture from browser devtools: Network ->
graphql -> request payload.

Note that a query using fragments -- SearchDatasets does -- is sent as the
operation followed by every fragment it reaches, transitively, each separated by
a blank line. `recover-queries` prints the operation alone, so the fragments must
be appended by hand; see `cap_client.recover` for how they are located.
"""

Q_CREATE_SESSION = "mutation CreateDatasetSession($data: SaveDatasetSessionInput!) {\n  saveDatasetSession(data: $data) {\n    id\n    name\n    description\n    datasetType\n    defaultEmbedding\n    cellCount\n    geneCount\n    labelsets {\n      id\n      order\n      status\n      mode\n      name\n      description\n      annotationMethod\n      algorithmName\n      algorithmVersion\n      algorithmRepoUrl\n      referenceLocation\n      referenceDescription\n      labels {\n        id\n        name\n        color\n        count\n        ontologyTermExists\n        ontologyTermId\n        ontologyTerm\n        fullName\n        categoryOntologyTermExists\n        categoryOntologyTermId\n        categoryOntologyTerm\n        categoryFullName\n        markerGenes\n        negativeMarkerGenes\n        canonicalMarkerGenes\n        synonyms\n        rationale\n        rationaleDois\n        ontologyAssessment\n        averageConfScore\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}"
Q_GENERAL_DE = "query GeneralDE($datasetId: ID!, $options: GetGeneralDiffInput!) {\n  datasetSession(datasetId: $datasetId) {\n    id\n    generalDifferentialExpressions(options: $options)\n    __typename\n  }\n}"
Q_DE_GENES = "query DEGenes($datasetId: ID!, $options: GetGenesBySelectionInput!) {\n  datasetSession(datasetId: $datasetId) {\n    id\n    diffGenesBySelection(options: $options) {\n      genes {\n        name\n        logFoldChange\n        score\n        pValue\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}"
Q_SELECTION = "query Selection($datasetId: ID!, $options: PostSingleSelectionKeyInput!) {\n  datasetSession(datasetId: $datasetId) {\n    id\n    singleSelectionKey(options: $options)\n    __typename\n  }\n}"
Q_CUSTOM_DIFF = "query CustomDiff($datasetId: ID!, $options: GetEmbeddingDiffInput!) {\n  datasetSession(datasetId: $datasetId) {\n    id\n    differentialExpressions(options: $options)\n    __typename\n  }\n}"
Q_EMBEDDING_DATA = "query EmbeddingData($datasetId: ID!, $options: GetDatasetEmbeddingDataInput!) {\n  datasetSession(datasetId: $datasetId) {\n    embeddingData(options: $options) {\n      obsIds\n      xyArray\n      xMax\n      xMin\n      yMax\n      yMin\n      annotations {\n        name\n        labelIds\n        __typename\n      }\n      geneExpression\n      expressionMax\n      expressionMin\n      __typename\n    }\n    __typename\n  }\n}"
Q_DOWNLOAD_URLS = "query DownloadUrls($datasetId: ID!) {\n  downloadUrls(datasetId: $datasetId) {\n    isAnnDataUrlUpToDate\n    annDataUrl\n    seuratUrl\n    capJsonUrlZip\n    capJsonUrlTar\n    __typename\n  }\n}"
Q_SEARCH_DATASETS = "query SearchDatasets($options: DatasetSearchOptions, $search: LookupDatasetsSearchInput, $filter: LookupDatasetsFiltersInput, $labelsetNames: [String!]) {\n  results: lookupDatasets(options: $options, search: $search, filter: $filter) {\n    id\n    name\n    ...DatasetResult\n    __typename\n  }\n}\n\nfragment DatasetResult on Dataset {\n  id\n  name\n  consortiumTags {\n    id\n    title\n    logoUrl\n    sortOrder\n    __typename\n  }\n  cellCount\n  labelsets(names: $labelsetNames) {\n    id\n    name\n    labels {\n      id\n      name\n      count\n      __typename\n    }\n    __typename\n  }\n  scores {\n    total\n    __typename\n  }\n  project {\n    id\n    name\n    createdAt\n    ...ProjectAuthors_project\n    __typename\n  }\n  __typename\n}\n\nfragment ProjectAuthors_project on Project {\n  version\n  permissions {\n    id\n    role\n    isActive\n    isContactPerson\n    user {\n      uid\n      displayName\n      avatarUrl\n      isDataCurator\n      __typename\n    }\n    __typename\n  }\n  externalAuthors {\n    name\n    email\n    isContactPerson\n    __typename\n  }\n  __typename\n}"
Q_CONSORTIUM_TAGS = "query SetProjectTagsDialogQuery($projectId: ID) {\n  consortiumTags {\n    id\n    title\n    parentId\n    sortOrder\n    __typename\n  }\n  project(projectId: $projectId) {\n    id\n    datasets {\n      id\n      consortiumTags {\n        id\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}"

ALL = {
    "CreateDatasetSession": Q_CREATE_SESSION,
    "GeneralDE": Q_GENERAL_DE,
    "DEGenes": Q_DE_GENES,
    "Selection": Q_SELECTION,
    "CustomDiff": Q_CUSTOM_DIFF,
    "EmbeddingData": Q_EMBEDDING_DATA,
    "DownloadUrls": Q_DOWNLOAD_URLS,
    "SearchDatasets": Q_SEARCH_DATASETS,
    # Registered under the operation name CAP's client uses. The name is
    # about a project-tagging dialog; the useful half is the root
    # `consortiumTags` field, which is why it is aliased here.
    "SetProjectTagsDialogQuery": Q_CONSORTIUM_TAGS,
}
