# AWS ECS Deployment Script for PowerShell
# This script builds, pushes, and deploys your Docker container to ECS

# Set variables
$AWS_REGION = "us-east-1"
$AWS_ACCOUNT_ID = "822815312360"
$ECR_REPO = "bb-chatbot"
$ECR_URL = "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO"
$CLUSTER_NAME = "BB-chatbot"
$SERVICE_NAME = "bb-chatbot-task-definition-service-ghlsbzt0"
$TASK_DEF_FAMILY = "bb-chatbot-task-definition"
$TASK_DEF_FILE = "ecs-task-def.json"

Write-Host "Starting deployment..." -ForegroundColor Green
Write-Host "ECR URL: $ECR_URL" -ForegroundColor Yellow
Write-Host "Cluster: $CLUSTER_NAME" -ForegroundColor Yellow
Write-Host "Service: $SERVICE_NAME" -ForegroundColor Yellow

# Check if task definition file exists
if (-not (Test-Path $TASK_DEF_FILE)) {
    Write-Host "Creating task definition file..." -ForegroundColor Yellow
    
    # Get current task definition and save to file
    try {
        $taskDef = aws ecs describe-task-definition --task-definition $TASK_DEF_FAMILY --query 'taskDefinition' --output json
        if ($LASTEXITCODE -eq 0) {
            $taskDef | Out-File -FilePath $TASK_DEF_FILE -Encoding utf8
            Write-Host "Task definition saved to $TASK_DEF_FILE" -ForegroundColor Green
        } else {
            Write-Host "Failed to get existing task definition. You may need to create $TASK_DEF_FILE manually." -ForegroundColor Red
            exit 1
        }
    } catch {
        Write-Host "Error getting task definition: $_" -ForegroundColor Red
        exit 1
    }
}

# 1. Authenticate Docker to ECR
Write-Host "Authenticating Docker to ECR..." -ForegroundColor Cyan
try {
    $loginCommand = aws ecr get-login-password --region $AWS_REGION
    if ($LASTEXITCODE -eq 0) {
        $loginCommand | docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Docker authentication successful" -ForegroundColor Green
        } else {
            Write-Host "Docker login failed" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "Failed to get ECR login token" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Error during ECR authentication: $_" -ForegroundColor Red
    exit 1
}

# 2. Build Docker image
Write-Host "Building Docker image..." -ForegroundColor Cyan
docker build -t $ECR_REPO .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker build failed" -ForegroundColor Red
    exit 1
}
Write-Host "Docker build successful" -ForegroundColor Green

# 3. Tag Docker image
Write-Host "Tagging Docker image..." -ForegroundColor Cyan
docker tag "$ECR_REPO`:latest" "$ECR_URL`:latest"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker tag failed" -ForegroundColor Red
    exit 1
}
Write-Host "Docker tag successful" -ForegroundColor Green

# 4. Push Docker image to ECR
Write-Host "Pushing Docker image to ECR..." -ForegroundColor Cyan
docker push "$ECR_URL`:latest"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker push failed" -ForegroundColor Red
    exit 1
}
Write-Host "Docker push successful" -ForegroundColor Green

# 5. Update the image URI in the task definition
Write-Host "Updating task definition with new image..." -ForegroundColor Cyan
try {
    $taskDefContent = Get-Content $TASK_DEF_FILE -Raw | ConvertFrom-Json
    
    # Update the image URI in the container definition
    foreach ($containerDef in $taskDefContent.containerDefinitions) {
        if ($containerDef.name -eq $ECR_REPO -or $containerDef.name -eq "bb-chatbot") {
            $containerDef.image = "$ECR_URL`:latest"
            Write-Host "Updated image URI to: $($containerDef.image)" -ForegroundColor Yellow
        }
    }
    
    # Remove fields that shouldn't be in the registration request
    $taskDefContent.PSObject.Properties.Remove('taskDefinitionArn')
    $taskDefContent.PSObject.Properties.Remove('revision')
    $taskDefContent.PSObject.Properties.Remove('status')
    $taskDefContent.PSObject.Properties.Remove('requiresAttributes')
    $taskDefContent.PSObject.Properties.Remove('placementConstraints')
    $taskDefContent.PSObject.Properties.Remove('compatibilities')
    $taskDefContent.PSObject.Properties.Remove('registeredAt')
    $taskDefContent.PSObject.Properties.Remove('registeredBy')
    
    # Save updated task definition using a method that guarantees no BOM
    $jsonString = $taskDefContent | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText((Resolve-Path $TASK_DEF_FILE).Path, $jsonString, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Task definition updated" -ForegroundColor Green
} catch {
    Write-Host "Error updating task definition: $_" -ForegroundColor Red
    exit 1
}

# 6. Register new ECS task definition revision
Write-Host "Registering new task definition..." -ForegroundColor Cyan
try {
    aws ecs register-task-definition --cli-input-json "file://$TASK_DEF_FILE"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Task definition registered successfully" -ForegroundColor Green
    } else {
        Write-Host "Failed to register task definition" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Error registering task definition: $_" -ForegroundColor Red
    exit 1
}

# 7. Get latest task definition revision ARN
Write-Host "Getting latest task definition ARN..." -ForegroundColor Cyan
try {
    $taskDefResponse = aws ecs describe-task-definition --task-definition $TASK_DEF_FAMILY --output json | ConvertFrom-Json
    if ($LASTEXITCODE -eq 0) {
        $taskDefArn = $taskDefResponse.taskDefinition.taskDefinitionArn
        Write-Host "Latest task definition ARN: $taskDefArn" -ForegroundColor Yellow
    } else {
        Write-Host "Failed to get task definition ARN" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Error getting task definition ARN: $_" -ForegroundColor Red
    exit 1
}

# 8. Update ECS service to use new task definition
Write-Host "Updating ECS service..." -ForegroundColor Cyan
try {
    aws ecs update-service --cluster $CLUSTER_NAME --service $SERVICE_NAME --task-definition $taskDefArn
    if ($LASTEXITCODE -eq 0) {
        Write-Host "ECS service updated successfully" -ForegroundColor Green
    } else {
        Write-Host "Failed to update ECS service" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "Error updating ECS service: $_" -ForegroundColor Red
    exit 1
}

Write-Host "Deployment completed successfully!" -ForegroundColor Green
Write-Host "You can check the deployment status in the AWS ECS Console." -ForegroundColor Yellow