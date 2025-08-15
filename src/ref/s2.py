#atualizou a função do patch

@app.patch("/experimentos/{experiment_id}/update-results")
def update_experiment_results(
    experiment_id: int,
    request: ResultsUpdateRequest,
    elab_url: str = Header(...),
    elab_api_key: str = Header(...)
):
    try:
        elab_service.update_results(
            elab_url, elab_api_key, True, experiment_id, request.results
        )
        # Mensagem de sucesso melhorada
        return {"status": "ok", "message": f"Resultados do experimento {experiment_id} atualizados e status alterado para 'Concluído' com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))