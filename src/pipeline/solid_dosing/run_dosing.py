from dosing_workflow import DosingWorkflowManager

SUBSTANCE_RECIPES = {
    "BDC":               (10,     "Milligram"),
    "KB":                (10,    "Milligram"),
    "MOF":               (100,   "Milligram"),
    "Aluminum Oxide":    (0.061, "Gram"),
    "Lithium Carbonate": (0.132, "Gram"),
}

def main():
    pipeline = DosingWorkflowManager(recipes=SUBSTANCE_RECIPES)
    pipeline.run()

if __name__ == "__main__":
    main()