class TaskDetail {
    constructor(
        taskId, taskStatus, officeWorkAlone, pendingSurveys, pendingList, surveyCompanyRepresentative, csrfToken, 
        billing, chargeId, typeTaskId, typeTaskName, useService) {

        this.csrfToken = csrfToken;
        this.taskId = taskId;        
        this.taskStatus = taskStatus;
        this.chargeId = chargeId;
        this.officeWorkAlone = (officeWorkAlone === 'True');
        this.pendingSurveys = pendingSurveys;
        this.pendingList = pendingList;
        this.surveyCompanyRepresentative=surveyCompanyRepresentative;
        this.billing = billing;
        this.typeTaskId = typeTaskId
        this.typeTask = typeTaskName;        
        this.expanded = false;            
        this.servicePriceTable = {};
        this.useService = useService === 'True' ? true : false;
        this._elTaskTitle = $('#task-title');
        this._elExecutionDate = $("input[name=execution_date]"); 
        this._elModalAction = $('#confirmAction');
        this._elRatingContainer = $('.rating-container');
        this._elFeedbackRating = $('#id_feedback_rating');
        this._elFeedbackComment = $('#id_feedback_comment');
        this._elModalActionButton = $('#actionButton');
        this._elModalNextText = $('#actionText');
        this._elModalHeader = $('#modalHeader');       
        this._elNotes = $('textarea[id=notes_id]');
        this._elBtnCompanyRepresentative = $('#btn-company_representative');
        this._elModalSurveyCompanyRepresentative = $("#survey-company-representative");
        this._elExecutionDate.attr({'required': true, 'placeholder': 'Data de Cumprimento'});        
        // Instancia da classe javascript que gera a tabela de precos
        this.priceTable;
        this.initFeedbackRating();
        this.initCpfCnpjField();        
        this.checkPaymentPending();
        this.onDocumentReady();
    }

    static createListItens(listItems) {
            let htmlListItens = '';
            for (var i = 0; i < listItems.length; i++) {
                htmlListItens += `<li>${listItems[i]}</li>`;
            }
            return htmlListItens;
        }

    get nextState() {
        return {
            REQUESTED: {text: "recusar", icon: "mdi mdi-clipboard-alert"},
            ACCEPTED_SERVICE: {text: "aceitar", icon: "mdi mdi-thumb-up-outline"},
            REFUSED_SERVICE: {text: "recusar", icon: "mdi mdi-thumb-down-outline"},
            OPEN: {text: "delegar", icon: "mdi mdi-account-location"},
            ACCEPTED: {text: "aceitar", icon: "mdi mdi-calendar-clock"},
            REFUSED: {text: "recusar", icon: "mdi mdi-clipboard-alert"},
            DELEGATED: {text: "delegar", icon: "assignment_returned"},
            DONE: {text: "Cumprir", icon: "mdi mdi-checkbox-marked-circle-outline"},
            FINISHED: {text: "Finalizar", icon: "mdi mdi-gavel"},
            BLOCKEDPAYMENT: {text: "Glosar", icon: "mdi mdi-currency-usd-off"},
            RETURN: {text: "Retornar", icon: "mdi mdi-backburger"}
        };
    }

    checkPaymentPending() {
        // Integração de pagamento removida (Gerencianet). Nada a verificar.
        return;
    }

    setExecutionDateRequire(status) {
        if (this._elExecutionDate.length > 0) {
            if (status === 'ACCEPTED'){
                this._elExecutionDate.attr('required', 'required');
                this._elExecutionDate.val('');

            }else{
                this._elExecutionDate.removeAttr('required');
            }
        }
    }

    checkExecutionDate(){
        if (this._elExecutionDate.length > 0) {
            let input = this._elExecutionDate.get(0);
            if (!input.checkValidity()) {
                input.reportValidity();
                return false;
            }
        }
    }

    showModalAction() {                
        if (this.taskStatus === 'ACCEPTED_SERVICE' || (this.taskStatus === 'REQUESTED' && !this.useService)) {
            if (this.priceTable) {
                delete this.priceTable
            }
            this.priceTable = new TaskDetailServicePriceTable(
                this.taskId, this.typeTask, this, null, this.csrfToken)        
            this.priceTable.bootstrap()
        } else {
            this._elModalAction.modal('show');
        }        
    }

    hideModalAction() {
        this._elModalAction.modal('hide');
    }

    showModalSurvey(el) {
        el.modal('show');
    }

    hideModalSurvey(el) {
        el.modal('hide');
    }

    validSurvey(status) {
        if(status === 'FINISHED' && this.pendingSurveys){
            let htmlList = `<ul class='font-15 text-left'>${TaskDetail.createListItens(this.pendingList)}</ul>`;
            let html = `<h4>A OS não pode ser finalizada porque o questionário do(s) participante(s) a seguir não foi 
                            respondido:</h4>
                        <br />${htmlList}`;
            swal({
                type: 'error',
                title: 'Questionário',
                html: html,
            });
        }        
    }

    showRatingContainer() {
        this._elRatingContainer.show();
    }

    hideRatingContainer() {
        this._elRatingContainer.hide();
        this._elFeedbackRating.rating('rate', '');
        this._elFeedbackComment.val('');        
    }

    makeRatingProccess(status) {
        if ((status === 'BLOCKEDPAYMENT' || status === 'FINISHED') && !(this.officeWorkAlone)) {
            this.showRatingContainer();
        } else {
            this.hideRatingContainer();
        }
    }

    configNotesField(status) {        
        /*Apenas estes status devem possuir notes como required, alem de nao poder 
         espacos em branco */        
        this._elNotes.removeAttr('required');        
        ['REQUESTED', 'REFUSED', 'BLOCKEDPAYMENT', 'RETURN', 'REFUSED_SERVICE'].forEach((s) => {
            if (status === s) {
                this._elNotes.attr('required', true).change(() => {
                    this._elNotes.val(this._elNotes.val().trim());
                });
            }
        });
    }

    formatModalAction(status) {        
        this._elModalNextText.innerHTML = this.nextState[status]['text'];
        $('#icon').addClass(this.nextState[status]['icon']);
        actionButton.innerHTML = "<i class='"+this.nextState[status]['icon']+"'></i> "+
            this.nextState[status]['text'].replace(this.nextState[status]['text'][0],
                this.nextState[status]['text'][0].toUpperCase());
        this._elModalActionButton.attr('name', 'action');
        this._elModalActionButton.attr('value', status);
    }

    initFeedbackRating() {
        this._elFeedbackRating.hide().rating({});
    }

    makeTaskAction(value) {        
        let taskStatus = value.id;
        this.validSurvey();
        this.makeRatingProccess(taskStatus);
        this.checkExecutionDate(taskStatus);
        this.showModalAction();
        this.formatModalAction(taskStatus);        
        this.configNotesField(taskStatus);
        return true;
    }

    initCpfCnpjField() {
        [].slice.call(document.querySelectorAll('.sttabs')).forEach(function(el) {
            new CBPFWTabs(el);
        });        
    }

    onClickBtnCompanyRepresentative() {
        this._elBtnCompanyRepresentative.on('click', (event)=>{
            if(this.surveyCompanyRepresentative) {
                this.showModalSurvey(this._elModalSurveyCompanyRepresentative)
            } else {
                swal({
                    type: 'error', 
                    title: 'Questionário',
                    text: "Não existe formulário cadastrado para este tipo de serviço."
                });                
            }
        });
    }

    toogleModals(modalToClose, modalToOpen, status) {
        $(modalToClose).one('hidden.bs.modal', function() {
            $('#survey').attr('data-status', status);
            $(modalToOpen).modal('show');
        }).modal('hide');
    }

    beforeSubmit(task_status) {
        this.toogleModals('#confirmAction', '#survey', task_status);
        $('#task_detail').submit(function (e) {
            e.preventDefault();
        });
        $('#actionButton').removeAttr('disabled');
    }        

// Todo: Ajustar de desmembrar
    submitTaskDetail(actionButton, use_service) {
        let task_status = actionButton.value;
        let have_survey = actionButton.getAttribute('survey');
        let ret;
        actionButton.disabled = true;
        if ((task_status === 'DONE' || task_status === 'FINISHED' && use_service === 'False') && have_survey){
            this.beforeSubmit(task_status);        
        } else{
            ret = true;
            $('#task_detail [required]').each(function(index) {
                if (!Boolean($( this ).val())){
                    actionButton.disabled = false;
                    ret = false;
                }
            });
            if (ret) {
                $('<input name="action" value="'+ task_status +'">').appendTo($('#task_detail'));
                this.toogleModals('#confirmAction', '#processing');
                $('#task_detail').unbind('submit').submit();
            }
        }
    }
    
    resetForm(el){
        el.form.reset();
        if ($('#id_feedback_rating').length > 0) {
            $('#id_feedback_rating').rating('rate', '');
        }
    }

    getLocation() {
        if (navigator.geolocation) {
            $('#locating').modal('show');
            navigator.geolocation.getCurrentPosition(this.showPosition, this.showError);
        } else {
            console.log("Geolocalização não é suportada pelo browser.");
        }
    }    

    showPosition(position, taskId) {
        var data = {};
        var checkpointtype = $('#GEOLOCATION').data("checkpointtype");
        data['latitude'] = position.coords.latitude;
        data['longitude'] = position.coords.longitude;        
        data['checkpointtype'] = checkpointtype;
        data['task_id'] = taskDetail.taskId;
        var url = $('#GEOLOCATION').data("url");
        $.ajax({
            type: 'POST',
            url: url,
            data: data,
            success: function (result) {
                console.log(result);
                if (result.ok){
                    location.reload();
                    $('#locating').modal('hide');
                }else{
                    $('#locating').modal('hide');
                    showToast('error', 'Atenção', "Localização não registrada", 0, false);
                }
            },
            error: function (request, status, error) {
            },
            beforeSend: function (xhr, settings) {
                xhr.setRequestHeader("X-CSRFToken", taskDetail.csrfToken);
            },
            dataType: 'json'
        })        
    }

    showError(error) {
        $('#locating').modal('hide');
        var msg = '';
        switch(error.code) {
            case error.PERMISSION_DENIED:
                msg = "O usuário negou o acesso à Geolocalização.";
                break;
            case error.POSITION_UNAVAILABLE:
                msg = "Informação de localização não disponível.";
                break;
            case error.TIMEOUT:
                msg = "Tempo limite atingido para o pedido de localização.";
                break;
            case error.UNKNOWN_ERROR:
                msg = "Ocorreu um erro desconhecido.";
                break;
        }
        showToast('error', 'Atenção', msg, 0, false);
    }    

    onKeypressAmountField() {
        $('input[id=id_amount]').keypress(function(e) {
            if(e.which == 13) {
              e.preventDefault();
            }
        });
    }

    onDocumentReady(){
	    $(document).ready(()=>{
	        if(this.taskStatus === 'ACCEPTED_SERVICE') {
                let url_string = window.location.href;
                let url = new URL(url_string);
                let action = url.searchParams.get("action");
                if (action === 'delegate') {                    
                    $('#OPEN').click();
                }
                if (action === 'assign') {
                    $('#ASSIGN').click();
                }
                this.onKeypressAmountField()
            }
	        this.setExecutionDateRequire(this.taskStatus);
        });
    }
    
    // Todo: Analisar e Levar para service-price-table.js
    delegateTaskPaid(gnData, intervalCheck) {
        if (gnData.status === 'paid' &&
            (this.taskStatus === 'ACCEPTED_SERVICE' || this.taskStatus === 'REQUESTED')) {
            clearInterval(intervalCheck);
            $.ajax({
                method: 'GET', 
                url: `/financeiro/tabelas-de-precos/detalhes/${gnData.custom_id}/`, 
                success: (response) => {
                    this.servicePriceTable = response;
                    console.log(response);
                    $.ajax({
                        method: 'post', 
                        url: `/providencias/${this.taskId}/batch/delegar`, 
                        data: {
                                task_id: this.taskId,
                                servicepricetable_id: response.id,   
                                amount: response.value,
                                amount_to_pay: response.value_to_pay,
                                amount_to_receive: response.value_to_receive,
                                note: '',                               
                            },
                        success: function(response) {                
                            if (response.status === 'ok') {
                                location.reload();
                            }
                        },
                        error: function (request, status, error) {
                        },
                        beforeSend: function (xhr, settings) {
                            xhr.setRequestHeader("X-CSRFToken", getCookie('csrftoken'));
                        },
                        dataType: 'json'                        
                    })                        
                }
            })                    
        }
    }
}

